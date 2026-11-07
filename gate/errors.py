"""Request errors returned as the §0 error JSON. Raised before any ledger row: nothing is attempted."""


class ApiError(Exception):
    def __init__(self, http, code, detail):
        super().__init__(detail)
        self.http, self.code, self.detail = http, code, detail
