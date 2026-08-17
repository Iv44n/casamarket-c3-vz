from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from .. import config


@dataclass(frozen=True)
class FormInfo:
    action: str | None
    method: str
    field_names: list[str]


@dataclass(frozen=True)
class DownloadButtonInfo:
    tag: str
    text: str
    href: str | None
    onclick: str | None
    data_type: str | None = None


@dataclass(frozen=True)
class ExportMechanism:
    export_endpoint: str
    massive_endpoint: str
    method: str
    date_param_format: str
    type_param_value: str
    query_params: list[str]
    notes: str
    selected_download_type: str = "FORM"


EXPORT_MECHANISMS = {
    "attention": ExportMechanism(
        export_endpoint="/user/report_message/attentions-export",
        massive_endpoint="/user/report_message/attentions-massive",
        method="GET",
        date_param_format="YYYY-MM-DD HH:mm (ej. 2026-08-11 00:00)",
        type_param_value="INBOUND",
        query_params=[
            "date_init", "date_end", "agent", "campaign", "attention_id",
            "number", "whatsapp_number_id", "status", "type", "condition",
            "message", "vip_only", "labels", "with_form",
        ],
        notes=(
            "Boton 'Exportar' -> 3 opciones (.export-option, data-type):\n"
            "  - NONE ('Solo exportar') y FORM ('Incluir formulario', with_form=1): "
            "GET a export_endpoint, disparado con window.open(url, '_blank') "
            "-> descarga sincrona, el navegador recibe el archivo directo.\n"
            "  - MASSIVE ('Generar reporte masivo'): GET AJAX a massive_endpoint, "
            "responde JSON con un mensaje; el archivo (zip de PDFs) se genera "
            "en background y se recoge despues en /user/report_general/masive_downloads "
            "-> flujo ASINCRONO (encolar / avisa que puede tardar horas).\n"
            "  - date_init/date_end por defecto: hoy 00:00 a hoy 23:59 (reporte del dia).\n"
            "  - Hay un limite de meses en el rango (exportLimitMonths, JS) y se bloquea "
            "si la tabla no tiene filas (numRows == 0)."
        ),
    ),
    "outboundattention": ExportMechanism(
        export_endpoint="/user/report_message/attentions-export",
        massive_endpoint="/user/report_message/attentions-massive",
        method="GET",
        date_param_format="YYYY-MM-DD HH:mm (ej. 2026-08-11 00:00)",
        type_param_value="OUTBOUND",
        query_params=[
            "date_init", "date_end", "agent", "campaign", "attention_id",
            "number", "whatsapp_number_id", "status", "type", "condition",
            "message", "vip_only", "labels", "with_form",
        ],
        notes="Igual que 'attention', solo cambia type=OUTBOUND. Ver appoutbound.js.",
    ),
}


@dataclass(frozen=True)
class CallExportMechanism:
    type_export_value: str
    extra_params: dict
    selected_with: str = "FORM"


CALLS_EXPORT_ENDPOINT = "/user/report/calls/export"
CALLS_MASSIVE_ENDPOINT = "/user/report/calls/massive"

CALL_EXPORT_MECHANISMS = {
    "callincoming": CallExportMechanism(
        type_export_value="incoming",
        extra_params={"vip_only": "false"},
    ),
    "calloutgoing": CallExportMechanism(
        type_export_value="outgoing",
        extra_params={"manual_dialer_id": "0", "dialer_id": "0"},
    ),
}

CONTACTS_EXPORT_ENDPOINT = "/user/contacts/export"

CONTACTS_EXPORT_DEFAULT_PARAMS = {
    "include_inactives": 0,
    "name": "",
    "doc_number": "",
    "company_id": "ALL",
    "contact": "",
}

TRANSFER_EXPORT_ENDPOINT = "/user/report_message/transfer/export"

TRANSFER_EXPORT_DEFAULT_PARAMS = {
    "agent_id_origin": "",
    "dest_type": "",
    "dest_id": "",
    "number": "",
    "status": "",
}

MASSIVE_LIST_ENDPOINT = "/user/report_general/get_massives"


@dataclass(frozen=True)
class ReportInspection:
    name: str
    path: str
    status_code: int
    forms: list[FormInfo] = field(default_factory=list)
    download_candidates: list[DownloadButtonInfo] = field(default_factory=list)
    html_dump_path: str | None = None
    export_mechanism: ExportMechanism | None = None


_DOWNLOAD_HINTS = ("descargar", "download", "exportar", "export")


def _forms_in(soup: BeautifulSoup) -> list[FormInfo]:
    forms = []
    for form in soup.find_all("form"):
        fields = [
            el.get("name")
            for el in form.find_all(["input", "select", "textarea"])
            if el.get("name")
        ]
        forms.append(
            FormInfo(
                action=form.get("action"),
                method=(form.get("method") or "GET").upper(),
                field_names=fields,
            )
        )
    return forms


def _download_candidates_in(soup: BeautifulSoup) -> list[DownloadButtonInfo]:
    seen_ids = set()
    candidates = []

    def add(el):
        if id(el) in seen_ids:
            return
        seen_ids.add(id(el))
        candidates.append(
            DownloadButtonInfo(
                tag=el.name,
                text=el.get_text(strip=True),
                href=el.get("href"),
                onclick=el.get("onclick"),
                data_type=el.get("data-type"),
            )
        )

    for el in soup.find_all(["a", "button"], class_="export-option"):
        add(el)

    for el in soup.find_all(["a", "button"]):
        text = el.get_text(strip=True).lower()
        onclick = el.get("onclick")
        haystack = " ".join(filter(None, [text, onclick or ""])).lower()
        if any(hint in haystack for hint in _DOWNLOAD_HINTS):
            add(el)

    return candidates


def inspect_report(client: httpx.Client, name: str, path: str) -> ReportInspection:
    response = client.get(path)
    response.raise_for_status()

    dump_path = config.RECON_DIR / f"{name}.html"
    config.RECON_DIR.mkdir(parents=True, exist_ok=True)
    dump_path.write_text(response.text, encoding="utf-8")

    soup = BeautifulSoup(response.text, "lxml")

    return ReportInspection(
        name=name,
        path=path,
        status_code=response.status_code,
        forms=_forms_in(soup),
        download_candidates=_download_candidates_in(soup),
        html_dump_path=str(dump_path),
        export_mechanism=EXPORT_MECHANISMS.get(name),
    )


def inspect_all(client: httpx.Client) -> list[ReportInspection]:
    return [
        inspect_report(client, name, path)
        for name, path in config.REPORT_PATHS.items()
    ]
