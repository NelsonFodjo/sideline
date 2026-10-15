"""JSON-RPC 2.0 and MCP error types.

Kept deliberately small. Every tool failure that is the *caller's* fault
becomes an InvalidParams; everything else becomes a ToolError, which the
server returns as a successful JSON-RPC response with `isError: true`,
per the MCP spec. That distinction matters: a tool that cannot find a
fixture has not broken the protocol, and Alexa+ should be able to tell
the listener so rather than see a transport failure.
"""

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class RpcError(Exception):
    code = INTERNAL_ERROR

    def __init__(self, message, data=None):
        super().__init__(message)
        self.message = message
        self.data = data

    def to_json(self):
        err = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


class ParseError(RpcError):
    code = PARSE_ERROR


class InvalidRequest(RpcError):
    code = INVALID_REQUEST


class MethodNotFound(RpcError):
    code = METHOD_NOT_FOUND


class InvalidParams(RpcError):
    code = INVALID_PARAMS


# What a listener hears when something went wrong that is not "there is no such match": the feed is down, a tool
# crashed, the model failed. Said the same way everywhere, and it tells them what to do next.
ERROR_SPOKEN = ("Sorry, an error occurred. Please try rephrasing your question for a better search, "
                "or try again later.")


class ToolError(Exception):
    """A tool ran but could not do the job.

    Returned to the model as content with isError=true so it can explain
    the situation to the listener instead of failing silently.
    """

    def __init__(self, spoken, detail=None):
        super().__init__(spoken)
        self.spoken = spoken
        self.detail = detail or {}
