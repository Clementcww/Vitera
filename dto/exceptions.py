class RFC9457ErrorResponse(Exception):
    def __init__(self, title: str, status: int, detail: str, instance: str):
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance

        super().__init__(title, status, detail, instance)


class InternalServerError(RFC9457ErrorResponse):
    def __init__(self, detail: str, instance: str):
        super().__init__(
            title="Internal Server Error", status=500, detail=detail, instance=instance
        )


class BadRequestError(RFC9457ErrorResponse):
    def __init__(self, detail: str, instance: str):
        super().__init__(
            title="Bad Request", status=400, detail=detail, instance=instance
        )


class RedactionError(RFC9457ErrorResponse):
    """PII survived redaction. Fail closed: nothing reaches the model."""

    def __init__(self, detail: str, instance: str):
        super().__init__(
            title="Redaction Failed", status=500, detail=detail, instance=instance
        )
