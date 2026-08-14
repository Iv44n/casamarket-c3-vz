from bs4 import BeautifulSoup

from app.c3 import reports


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def test_forms_in_extracts_action_method_and_fields():
    html = """
    <form action="/buscar" method="post">
        <input name="a">
        <select name="b"></select>
        <input type="hidden" name="_token" value="x">
    </form>
    """
    forms = reports._forms_in(_soup(html))

    assert len(forms) == 1
    assert forms[0].action == "/buscar"
    assert forms[0].method == "POST"
    assert forms[0].field_names == ["a", "b", "_token"]


def test_forms_in_defaults_method_to_get():
    forms = reports._forms_in(_soup("<form><input name='x'></form>"))

    assert forms[0].method == "GET"


def test_download_candidates_detects_export_option_by_data_type():
    html = """
    <button class="dropdown-item export-option" data-type="FORM">Incluir formulario</button>
    """
    candidates = reports._download_candidates_in(_soup(html))

    assert len(candidates) == 1
    assert candidates[0].data_type == "FORM"
    assert candidates[0].text == "Incluir formulario"


def test_download_candidates_detects_by_text_heuristic_without_export_option_class():
    html = '<a href="#" onclick="doExportSomething()">Descargar reporte</a>'
    candidates = reports._download_candidates_in(_soup(html))

    assert len(candidates) == 1
    assert candidates[0].tag == "a"


def test_download_candidates_ignores_unrelated_buttons():
    html = '<button onclick="save()">Guardar</button>'
    candidates = reports._download_candidates_in(_soup(html))

    assert candidates == []


def test_download_candidates_does_not_duplicate_same_element():
    html = '<button class="export-option" data-type="NONE">Solo exportar</button>'
    candidates = reports._download_candidates_in(_soup(html))

    assert len(candidates) == 1


def test_attention_and_outbound_share_endpoint_but_differ_in_type():
    attention = reports.EXPORT_MECHANISMS["attention"]
    outbound = reports.EXPORT_MECHANISMS["outboundattention"]

    assert attention.export_endpoint == outbound.export_endpoint
    assert attention.type_param_value == "INBOUND"
    assert outbound.type_param_value == "OUTBOUND"


def test_export_mechanisms_default_to_form_variant():
    for mechanism in reports.EXPORT_MECHANISMS.values():
        assert mechanism.selected_download_type == "FORM"


def test_call_export_mechanisms_are_not_symmetric():
    incoming = reports.CALL_EXPORT_MECHANISMS["callincoming"]
    outgoing = reports.CALL_EXPORT_MECHANISMS["calloutgoing"]

    assert "vip_only" in incoming.extra_params
    assert "vip_only" not in outgoing.extra_params

    assert "manual_dialer_id" in outgoing.extra_params
    assert "dialer_id" in outgoing.extra_params
    assert "manual_dialer_id" not in incoming.extra_params

    assert incoming.selected_with == "FORM"
    assert outgoing.selected_with == "FORM"


def test_contacts_export_has_no_date_range_params():
    assert "date_init" not in reports.CONTACTS_EXPORT_DEFAULT_PARAMS
    assert reports.CONTACTS_EXPORT_DEFAULT_PARAMS["company_id"] == "ALL"
