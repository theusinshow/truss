"""Descoberta de gabaritos de calibracao e do PDF de cada um.

Um gabarito por projeto, um arquivo YAML por gabarito. Acrescentar um projeto a
calibracao e soltar o PDF e o YAML na pasta: nenhum teste referencia um arquivo
pelo nome.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
CALIBRATION_DIR = REPO_ROOT / "calibration"

# O PDF versionado do projeto-base fica em docs/; material importado localmente
# fica em data/originals, que nao vai para o repositorio.
DEFAULT_SEARCH_ROOTS = (REPO_ROOT / "docs" / "projeto_base", REPO_ROOT / "data" / "originals")

STATUS_HUMAN_VERIFIED = "human_verified"
STATUS_DRAFT = "draft_unverified"

# Um gabarito sem `status` declarado veio da saida do proprio pipeline. Trata-lo
# como verificado transformaria um detector de regressao em prova de correcao.
STATUS_LEGACY = "legacy"


@dataclass(frozen=True)
class GroundTruth:
    path: Path
    version: int
    status: str
    filename: str
    sha256: str | None
    page_count: int | None
    thresholds: dict
    sheets: list[dict]
    payload: dict

    @property
    def is_human_verified(self) -> bool:
        return self.status == STATUS_HUMAN_VERIFIED

    @property
    def name(self) -> str:
        return self.path.stem


def _to_ground_truth(path: Path) -> GroundTruth:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    document = payload.get("document", {})

    return GroundTruth(
        path=path,
        version=int(payload.get("version", 1)),
        status=str(payload.get("status", STATUS_LEGACY)),
        filename=str(document.get("filename", "")),
        sha256=document.get("sha256"),
        page_count=document.get("page_count"),
        thresholds=payload.get("thresholds", {}),
        sheets=payload.get("sheets", []),
        payload=payload,
    )


def load_ground_truths(directory: Path | None = None) -> list[GroundTruth]:
    return [_to_ground_truth(path) for path in sorted((directory or CALIBRATION_DIR).glob("*.yml"))]


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_reference_pdf(
    truth: GroundTruth,
    search_roots: list[Path] | tuple[Path, ...] | None = None,
) -> Path | None:
    """Localiza o PDF de um gabarito.

    Casa por hash de conteudo quando o gabarito declara um, porque a importacao
    sanitiza o nome do arquivo - troca espacos por hifens e prefixa o hash - e
    procurar pelo nome declarado falha justamente no arquivo que o proprio Truss
    guardou.
    """
    candidates = [
        path
        for root in (search_roots or DEFAULT_SEARCH_ROOTS)
        if Path(root).exists()
        for path in sorted(Path(root).rglob("*.pdf"))
    ]

    if truth.sha256:
        return next((path for path in candidates if _file_hash(path) == truth.sha256), None)

    if not truth.filename:
        return None

    return next((path for path in candidates if path.name.endswith(truth.filename)), None)
