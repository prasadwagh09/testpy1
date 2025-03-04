import json
import logging
from typing import Iterator, List, Optional, TypedDict, Union, cast
from urllib.parse import urlunparse

import requests
from typing_extensions import NotRequired

from snowflake import snowpark
from snowflake.cortex._sse_client import SSEClient
from snowflake.cortex._util import (
    CORTEX_FUNCTIONS_TELEMETRY_PROJECT,
    SnowflakeAuthenticationException,
    SnowflakeConfigurationException,
)
from snowflake.ml._internal import telemetry
from snowflake.snowpark import context, functions

logger = logging.getLogger(__name__)


class ConversationMessage(TypedDict):
    """Represents an conversation interaction."""

    role: str
    """The role of the participant. For example, "user" or "assistant"."""

    content: str
    """The content of the message."""


class CompleteOptions(TypedDict):
    """Options configuring a snowflake.cortex.Complete call."""

    max_tokens: NotRequired[int]
    """ Sets the maximum number of output tokens in the response. Small values can result in
    truncated responses. """
    temperature: NotRequired[float]
    """ A value from 0 to 1 (inclusive) that controls the randomness of the output of the language
    model. A higher temperature (for example, 0.7) results in more diverse and random output, while a lower
    temperature (such as 0.2) makes the output more deterministic and focused. """

    top_p: NotRequired[float]
    """ A value from 0 to 1 (inclusive) that controls the randomness and diversity of the language model,
    generally used as an alternative to temperature. The difference is that top_p restricts the set of possible tokens
    that the model outputs, while temperature influences which tokens are chosen at each step. """


class ResponseParseException(Exception):
    """This exception is raised when the server response cannot be parsed."""

    pass


def _call_complete_rest(
    model: str,
    prompt: Union[str, List[ConversationMessage]],
    options: Optional[CompleteOptions] = None,
    session: Optional[snowpark.Session] = None,
    stream: bool = False,
) -> requests.Response:
    session = session or context.get_active_session()
    if session is None:
        raise SnowflakeAuthenticationException(
            """Session required. Provide the session through a session=... argument or ensure an active session is
            available in your environment."""
        )

    if session.connection.host is None or session.connection.host == "":
        raise SnowflakeConfigurationException("Snowflake connection configuration does not specify 'host'")

    if session.connection.rest is None or not hasattr(session.connection.rest, "token"):
        raise SnowflakeAuthenticationException("Snowflake session error: REST token missing.")

    if session.connection.rest.token is None or session.connection.rest.token == "":
        raise SnowflakeAuthenticationException("Snowflake session error: REST token is empty.")

    scheme = "https"
    if hasattr(session.connection, "scheme"):
        scheme = session.connection.scheme
    url = urlunparse((scheme, session.connection.host, "api/v2/cortex/inference/complete", "", "", ""))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f'Snowflake Token="{session.connection.rest.token}"',
        "Accept": "application/json, text/event-stream",
    }

    data = {
        "model": model,
        "stream": stream,
    }
    if isinstance(prompt, List):
        data["messages"] = prompt
    else:
        data["messages"] = [{"content": prompt}]

    if options:
        if "max_tokens" in options:
            data["max_tokens"] = options["max_tokens"]
            data["max_output_tokens"] = options["max_tokens"]
        if "temperature" in options:
            data["temperature"] = options["temperature"]
        if "top_p" in options:
            data["top_p"] = options["top_p"]

    logger.debug(f"making POST request to {url} (model={model}, stream={stream})")
    response = requests.post(
        url,
        json=data,
        headers=headers,
        stream=stream,
    )
    response.raise_for_status()
    return response


def _process_rest_response(response: requests.Response, stream: bool = False) -> Union[str, Iterator[str]]:
    if stream:
        return _return_stream_response(response)

    try:
        content = response.json()["choices"][0]["message"]["content"]
        assert isinstance(content, str)
        return content
    except (KeyError, IndexError, AssertionError) as e:
        # Unlike the streaming case, errors are not ignored because a message must be returned.
        raise ResponseParseException("Failed to parse message from response.") from e


def _return_stream_response(response: requests.Response) -> Iterator[str]:
    client = SSEClient(response)
    for event in client.events():
        try:
            yield json.loads(event.data)["choices"][0]["delta"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError):
            # For the sake of evolution of the output format,
            # ignore stream messages that don't match the expected format.
            pass


def _complete_call_sql_function_snowpark(
    function: str, *args: Union[str, snowpark.Column, CompleteOptions]
) -> snowpark.Column:
    return cast(snowpark.Column, functions.builtin(function)(*args))


def _complete_call_sql_function_immediate(
    function: str,
    model: str,
    prompt: Union[str, List[ConversationMessage]],
    options: Optional[CompleteOptions],
    session: Optional[snowpark.Session],
) -> str:
    session = session or context.get_active_session()
    if session is None:
        raise SnowflakeAuthenticationException(
            """Session required. Provide the session through a session=... argument or ensure an active session is
            available in your environment."""
        )

    # https://docs.snowflake.com/en/sql-reference/functions/complete-snowflake-cortex
    if options is not None or not isinstance(prompt, str):
        if isinstance(prompt, List):
            prompt_arg = prompt
        else:
            prompt_arg = [{"role": "user", "content": prompt}]
        options = options or {}
        lit_args = [
            functions.lit(model),
            functions.lit(prompt_arg),
            functions.lit(options),
        ]
    else:
        lit_args = [
            functions.lit(model),
            functions.lit(prompt),
        ]

    empty_df = session.create_dataframe([snowpark.Row()])
    df = empty_df.select(functions.builtin(function)(*lit_args))
    return cast(str, df.collect()[0][0])


def _complete_sql_impl(
    function: str,
    model: Union[str, snowpark.Column],
    prompt: Union[str, List[ConversationMessage], snowpark.Column],
    options: Optional[Union[CompleteOptions, snowpark.Column]],
    session: Optional[snowpark.Session],
) -> Union[str, snowpark.Column]:
    if isinstance(prompt, snowpark.Column):
        if options is not None:
            return _complete_call_sql_function_snowpark(function, model, prompt, options)
        else:
            return _complete_call_sql_function_snowpark(function, model, prompt)
    if isinstance(model, snowpark.Column):
        raise ValueError("'model' cannot be a snowpark.Column when 'prompt' is a string.")
    if isinstance(options, snowpark.Column):
        raise ValueError("'options' cannot be a snowpark.Column when 'prompt' is a string.")
    return _complete_call_sql_function_immediate(function, model, prompt, options, session)


def _complete_impl(
    model: Union[str, snowpark.Column],
    prompt: Union[str, List[ConversationMessage], snowpark.Column],
    options: Optional[CompleteOptions] = None,
    session: Optional[snowpark.Session] = None,
    use_rest_api_experimental: bool = False,
    stream: bool = False,
    function: str = "snowflake.cortex.complete",
) -> Union[str, Iterator[str], snowpark.Column]:
    if use_rest_api_experimental:
        if not isinstance(model, str):
            raise ValueError("in REST mode, 'model' must be a string")
        if not isinstance(prompt, str) and not isinstance(prompt, List):
            raise ValueError("in REST mode, 'prompt' must be a string or a list of ConversationMessage")
        response = _call_complete_rest(model, prompt, options, session=session, stream=stream)
        return _process_rest_response(response, stream=stream)
    if stream is True:
        raise ValueError("streaming can only be enabled in REST mode, set use_rest_api_experimental=True")
    return _complete_sql_impl(function, model, prompt, options, session)


@telemetry.send_api_usage_telemetry(
    project=CORTEX_FUNCTIONS_TELEMETRY_PROJECT,
)
def Complete(
    model: Union[str, snowpark.Column],
    prompt: Union[str, List[ConversationMessage], snowpark.Column],
    *,
    options: Optional[CompleteOptions] = None,
    session: Optional[snowpark.Session] = None,
    use_rest_api_experimental: bool = False,
    stream: bool = False,
) -> Union[str, Iterator[str], snowpark.Column]:
    """Complete calls into the LLM inference service to perform completion.

    Args:
        model: A Column of strings representing model types.
        prompt: A Column of prompts to send to the LLM.
        options: A instance of snowflake.cortex.CompleteOptions
        session: The snowpark session to use. Will be inferred by context if not specified.
        use_rest_api_experimental (bool): Toggles between the use of SQL and REST implementation. This feature is
            experimental and can be removed at any time.
        stream (bool): Enables streaming. When enabled, a generator function is returned that provides the streaming
            output as it is received. Each update is a string containing the new text content since the previous update.
            The use of streaming requires the experimental use_rest_api_experimental flag to be enabled.

    Raises:
        ValueError: If `stream` is set to True and `use_rest_api_experimental` is set to False.

    Returns:
        A column of string responses.
    """
    try:
        return _complete_impl(model, prompt, options, session, use_rest_api_experimental, stream)
    except ValueError as err:
        raise err
