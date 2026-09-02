from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PublicError:
    code: str
    message: str
    action: str
    retryable: bool = False
    operation_id: str | None = None

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "action": self.action,
            "retryable": self.retryable,
            "operation_id": self.operation_id,
        }


class TrussError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        action: str,
        status_code: int = 500,
        retryable: bool = False,
        operation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.public = PublicError(
            code=code,
            message=message,
            action=action,
            retryable=retryable,
            operation_id=operation_id,
        )
        self.status_code = status_code


def storage_error(error: OSError, *, operation_id: str | None = None) -> TrussError:
    if getattr(error, "errno", None) == 28:
        return TrussError(
            code="STORAGE_FULL",
            message="Nao ha espaco suficiente para concluir a operacao.",
            action="Libere espaco no disco e continue a operacao.",
            status_code=507,
            retryable=True,
            operation_id=operation_id,
        )
    if getattr(error, "errno", None) in {1, 13, 30}:
        return TrussError(
            code="STORAGE_NOT_WRITABLE",
            message="O armazenamento local nao permite escrita.",
            action="Verifique as permissoes e se o disco esta em modo somente leitura.",
            status_code=507,
            retryable=True,
            operation_id=operation_id,
        )
    return TrussError(
        code="STORAGE_IO_ERROR",
        message="O armazenamento local falhou durante a operacao.",
        action="Execute o diagnostico local antes de tentar novamente.",
        status_code=500,
        retryable=True,
        operation_id=operation_id,
    )

