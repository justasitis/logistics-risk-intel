"""
B-LAP 일정 이상탐지 전용 Denodo 클라이언트.
- VDT_INB_BL_INFO: 현재 선적 Snapshot
- VDT_INB_BL_HIS: ETD/ETA 변경 이력
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Iterable, Optional, Sequence

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

DEFAULT_BASE_URL = os.environ.get("DATALAKE_BASE_URL", "http://dnd.datalake.sk-on.com:9443")
INFO_VIEW_PATH = "/denodo-restfulws/hq_intg/views/vdt_inb_bl_info"
HISTORY_VIEW_PATH = "/denodo-restfulws/hq_intg/views/vdt_inb_bl_his"
DEFAULT_TIMEOUT = int(os.environ.get("DATALAKE_TIMEOUT", "30"))
DEFAULT_USERNAME = os.environ.get("DATALAKE_USERNAME", "")
DEFAULT_PASSWORD = os.environ.get("DATALAKE_PASSWORD", "")

INFO_SELECT_COLUMNS = [
    "cmpy_cd", "cmpy_nm", "plnt_cd", "plnt_nm",
    "lsp_cd", "lsp_nm", "sppl_cd", "sppl_nm",
    "bsns_ccd", "bsns_ccd_nm", "trpr_no", "trpr_mode",
    "carrier_cd", "carrier_nm", "po_no", "item_no", "item_cd", "item_nm",
    "dlvy_req_date", "dlvy_qty", "dlvy_unit", "booking_no", "vessel_nm",
    "voyage_no", "hbl_no", "mbl_no", "cntr_no", "dprt", "dprt_nm",
    "cargo_type3",
    "onboard_date",
    "etd", "atd", "arvl", "arvl_nm", "eta", "eta_date", "ata",
    "to_stlc_cd", "to_stlc_nm", "dlvy_eta", "dlvy_ata", "final_pod",
    "final_pod_nm", "final_pod_eta_date", "cmpl_yn", "clsn_yn",
    "etd_his", "eta_his", "stopby", "stopby_nm", "rmrk",
]

HISTORY_SELECT_COLUMNS = [
    "cmpy_cd", "plnt_cd", "trpr_no", "his_type", "his_no",
    "fr_date", "to_date", "ins_datetime", "ins_person_id",
]

# 법인 이름(cmpy_nm, UI 표기) ↔ 법인 코드(cmpy_cd) 매핑 — 단일 정의처.
# 프런트 법인 필터는 이름 표기(SKO/SKBA/...)를 본번호와 혼용할 수 있으므로
# 양쪽 모두 받아 cmpy_nm 기준으로 정규화한다.
COMPANY_NAME_TO_CODE = {
    "SKO": "S000",
    "SKOH": "S210",
    "SKBM": "S220",
    "SKBA": "S330",
    "SKOJ": "S930",
    "SKOY": "S950",
}
COMPANY_CODE_TO_NAME = {
    code: name for name, code in COMPANY_NAME_TO_CODE.items()
}


def normalize_company_name(value: Any) -> str:
    """법인 코드(S000)가 들어오면 이름(SKO)으로 변환. 미등록 값은 원형 유지."""
    text = str(value or "").strip()
    return COMPANY_CODE_TO_NAME.get(text.upper(), text)


def normalize_company_code(value: Any) -> str:
    """법인 이름(SKO)이 들어오면 코드(S000)로 변환. 미등록 값은 원형 유지."""
    text = str(value or "").strip()
    return COMPANY_NAME_TO_CODE.get(text.upper(), text)

INFO_DATE_COLUMNS = [
    "dlvy_req_date", "onboard_date", "etd", "atd", "eta", "eta_date", "ata",
    "dlvy_eta", "dlvy_ata", "final_pod_eta_date",
]
HISTORY_DATE_COLUMNS = ["fr_date", "to_date", "ins_datetime"]


def _require_credentials(username: Optional[str], password: Optional[str]) -> tuple[str, str]:
    user = username or DEFAULT_USERNAME
    pwd = password or DEFAULT_PASSWORD
    if not user or not pwd:
        raise RuntimeError(
            "데이터레이크 인증정보가 없습니다. "
            "DATALAKE_USERNAME, DATALAKE_PASSWORD 환경변수를 설정하세요."
        )
    return user, pwd


def _escape_literal(value: Any) -> str:
    return str(value).replace("'", "''")


def _parse_payload_to_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # 봉투 키가 "존재하는지"로 판별한다. `or` 체인으로 찾으면
        # {"elements": []} 같은 빈 결과 페이지가 falsy라서 빠져나가
        # 봉투 자체를 1행으로 반환하는 오류가 있었다 (SKO처럼 조회
        # 결과가 없는 History chunk에서 "필수 컬럼 누락" 오류 유발).
        for key in ("elements", "data", "rows", "result"):
            if key in payload:
                rows = payload[key]
                if isinstance(rows, dict):
                    return [rows]
                if isinstance(rows, list):
                    return rows
                return []
        return [payload]
    raise RuntimeError(f"예상치 못한 Denodo 응답 형태: {type(payload)}")


def _parse_datetime_value(value: Any) -> pd.Timestamp:
    if value is None:
        return pd.NaT
    try:
        if pd.isna(value):
            return pd.NaT
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return pd.NaT
    if len(text) >= 8 and text[:8].isdigit():
        try:
            if len(text) >= 14 and text[:14].isdigit():
                return pd.to_datetime(text[:14], format="%Y%m%d%H%M%S")
            return pd.to_datetime(text[:8], format="%Y%m%d")
        except (TypeError, ValueError):
            pass
    return pd.to_datetime(text, errors="coerce")


def _convert_date_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = result[column].map(_parse_datetime_value)
    return result


def _fetch_view(
    *,
    view_path: str,
    select_columns: Sequence[str],
    filter_expr: Optional[str] = None,
    max_rows: int = 50_000,
    page_size: int = 1_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    user, pwd = _require_credentials(username, password)
    auth = HTTPBasicAuth(user, pwd)
    all_rows: list[dict[str, Any]] = []
    start_index = 0

    while start_index < max_rows:
        count = min(page_size, max_rows - start_index)
        params: dict[str, Any] = {
            "$format": "json",
            "$select": ",".join(select_columns),
            "$start_index": start_index,
            "$count": count,
        }
        if filter_expr:
            params["$filter"] = filter_expr

        response: Optional[requests.Response] = None
        try:
            response = requests.get(
                f"{base_url.rstrip('/')}{view_path}",
                params=params,
                auth=auth,
                timeout=timeout,
            )
            response.raise_for_status()
            rows = _parse_payload_to_rows(response.json())
        except requests.exceptions.HTTPError as exc:
            status = response.status_code if response is not None else "?"
            if status == 401:
                raise RuntimeError("데이터레이크 인증 실패") from exc
            detail = response.text[:300] if response is not None else str(exc)
            raise RuntimeError(f"Denodo HTTP 오류 {status}: {detail}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"데이터레이크 연결 실패: {base_url}{view_path}") from exc
        except requests.exceptions.Timeout as exc:
            raise RuntimeError(f"데이터레이크 응답 타임아웃: {timeout}초") from exc
        except ValueError as exc:
            raise RuntimeError("Denodo JSON 응답 파싱 실패") from exc

        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < count:
            break
        start_index += count

    return pd.DataFrame(all_rows)


def fetch_bl_info(
    *,
    etd_from: Optional[date] = None,
    companies: Optional[Sequence[str]] = None,
    plants: Optional[Sequence[str]] = None,
    max_rows: int = 20_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> pd.DataFrame:
    filters: list[str] = []
    if etd_from:
        filters.append(f"etd >= '{etd_from.strftime('%Y-%m-%d')}'")
    if companies:
        expr = " or ".join(
            f"cmpy_nm = '{_escape_literal(normalize_company_name(v))}'"
            for v in companies
        )
        filters.append(f"({expr})")
    if plants:
        expr = " or ".join(f"plnt_cd = '{_escape_literal(v)}'" for v in plants)
        filters.append(f"({expr})")

    df = _fetch_view(
        view_path=INFO_VIEW_PATH,
        select_columns=INFO_SELECT_COLUMNS,
        filter_expr=" and ".join(filters) if filters else None,
        max_rows=max_rows,
        username=username,
        password=password,
    )
    return _convert_date_columns(df, INFO_DATE_COLUMNS)


def fetch_bl_history(
    *,
    changed_from: Optional[date] = None,
    changed_to: Optional[date] = None,
    company_codes: Optional[Sequence[str]] = None,
    plant_codes: Optional[Sequence[str]] = None,
    max_rows: int = 50_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> pd.DataFrame:
    filters: list[str] = []
    if changed_from:
        filters.append(f"ins_datetime >= '{changed_from.strftime('%Y-%m-%d')}'")
    if changed_to:
        filters.append(f"ins_datetime < '{changed_to.strftime('%Y-%m-%d')}'")
    if company_codes:
        expr = " or ".join(
            f"cmpy_cd = '{_escape_literal(normalize_company_code(v))}'"
            for v in company_codes
        )
        filters.append(f"({expr})")
    if plant_codes:
        expr = " or ".join(f"plnt_cd = '{_escape_literal(v)}'" for v in plant_codes)
        filters.append(f"({expr})")

    df = _fetch_view(
        view_path=HISTORY_VIEW_PATH,
        select_columns=HISTORY_SELECT_COLUMNS,
        filter_expr=" and ".join(filters) if filters else None,
        max_rows=max_rows,
        username=username,
        password=password,
    )
    return _convert_date_columns(df, HISTORY_DATE_COLUMNS)


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]



def _normalized_code(value: Any) -> str:
    return str(value or "").strip()


def _remap_history_transport_keys(
    frame: pd.DataFrame,
    requested_keys: Sequence[tuple[str, str, str]],
) -> pd.DataFrame:
    """
    History 테이블의 cmpy_cd/plnt_cd 표현이 Snapshot과 다르더라도
    Transportation No.가 유일하면 Snapshot Key로 정렬한다.

    원본 코드는 source_cmpy_cd/source_plnt_cd에 보존한다.
    """
    if frame.empty:
        return frame

    key_candidates: dict[str, set[tuple[str, str]]] = {}
    for cmpy_cd, plnt_cd, trpr_no in requested_keys:
        transport_no = _normalized_code(trpr_no)
        if not transport_no:
            continue
        key_candidates.setdefault(transport_no, set()).add(
            (
                _normalized_code(cmpy_cd),
                _normalized_code(plnt_cd),
            )
        )

    unique_key_by_transport = {
        trpr_no: next(iter(values))
        for trpr_no, values in key_candidates.items()
        if len(values) == 1
    }

    result = frame.copy()

    for column in ["cmpy_cd", "plnt_cd", "trpr_no"]:
        if column not in result.columns:
            result[column] = ""
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    result["source_cmpy_cd"] = result["cmpy_cd"]
    result["source_plnt_cd"] = result["plnt_cd"]

    for index, row in result.iterrows():
        transport_no = _normalized_code(row.get("trpr_no"))
        requested = unique_key_by_transport.get(transport_no)
        if requested is None:
            continue

        requested_company, requested_plant = requested
        if requested_company:
            result.at[index, "cmpy_cd"] = requested_company
        if requested_plant:
            result.at[index, "plnt_cd"] = requested_plant

    return result


def fetch_bl_history_for_transports(
    transport_keys: Sequence[tuple[str, str, str]],
    *,
    changed_from: Optional[date] = None,
    chunk_size: int = 20,
    max_rows_per_chunk: int = 10_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> pd.DataFrame:
    """
    여러 Transportation No.의 이력을 조회한다.

    중요:
    Denodo 원천 History의 cmpy_cd/plnt_cd가 Snapshot과 다를 수 있으므로
    원천 조회 조건은 trpr_no만 사용한다. 조회 후 Transportation No.가
    유일한 경우 Snapshot의 회사/Plant Key로 재매핑한다.
    """
    normalized_keys = sorted({
        (
            _normalized_code(cmpy_cd),
            _normalized_code(plnt_cd),
            _normalized_code(trpr_no),
        )
        for cmpy_cd, plnt_cd, trpr_no in transport_keys
        if _normalized_code(trpr_no)
    })

    if not normalized_keys:
        return pd.DataFrame(columns=HISTORY_SELECT_COLUMNS)

    frames: list[pd.DataFrame] = []

    for key_chunk in _chunked(normalized_keys, chunk_size):
        transport_numbers = sorted({
            trpr_no
            for _, _, trpr_no in key_chunk
            if trpr_no
        })

        transport_expr = " or ".join(
            f"trpr_no = '{_escape_literal(trpr_no)}'"
            for trpr_no in transport_numbers
        )

        filters = [f"({transport_expr})"]

        if changed_from:
            filters.append(
                "ins_datetime >= "
                f"'{changed_from.strftime('%Y-%m-%d')}'"
            )

        frame = _fetch_view(
            view_path=HISTORY_VIEW_PATH,
            select_columns=HISTORY_SELECT_COLUMNS,
            filter_expr=" and ".join(filters),
            max_rows=max_rows_per_chunk,
            username=username,
            password=password,
        )

        if frame.empty:
            continue

        frame = _remap_history_transport_keys(
            frame,
            key_chunk,
        )
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=HISTORY_SELECT_COLUMNS)

    result = pd.concat(frames, ignore_index=True)

    duplicate_columns = [
        "cmpy_cd",
        "plnt_cd",
        "trpr_no",
        "his_type",
        "his_no",
    ]
    duplicate_columns = [
        column
        for column in duplicate_columns
        if column in result.columns
    ]

    if duplicate_columns:
        result = result.drop_duplicates(
            subset=duplicate_columns,
            keep="last",
        )

    return _convert_date_columns(
        result,
        HISTORY_DATE_COLUMNS,
    )


def _prefer_exact_transport_codes(
    frame: pd.DataFrame,
    *,
    cmpy_cd: Optional[str],
    plnt_cd: Optional[str],
) -> pd.DataFrame:
    """
    회사/Plant가 정확히 일치하는 행이 있으면 우선 사용한다.
    일치행이 없다는 이유로 trpr_no 조회 결과 전체를 버리지는 않는다.
    """
    if frame.empty:
        return frame

    result = frame.copy()

    for column in ["cmpy_cd", "plnt_cd"]:
        if column not in result.columns:
            result[column] = ""
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    requested_company = _normalized_code(cmpy_cd)
    requested_plant = _normalized_code(plnt_cd)

    if requested_company:
        company_rows = result.loc[
            result["cmpy_cd"].eq(requested_company)
        ].copy()
        if not company_rows.empty:
            result = company_rows

    if requested_plant:
        plant_rows = result.loc[
            result["plnt_cd"].eq(requested_plant)
        ].copy()
        if not plant_rows.empty:
            result = plant_rows

    return result


def fetch_bl_history_for_transport(
    trpr_no: str,
    *,
    cmpy_cd: Optional[str] = None,
    plnt_cd: Optional[str] = None,
    changed_from: Optional[date] = None,
    max_rows: int = 20_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> pd.DataFrame:
    """
    특정 Transportation No.의 전체 History를 조회한다.

    Denodo 필터는 trpr_no만 사용하고, cmpy_cd/plnt_cd는 조회 후
    정확히 일치하는 행이 있을 때만 우선 필터로 적용한다.
    """
    transport_no = _normalized_code(trpr_no)
    if not transport_no:
        raise ValueError("trpr_no는 필수입니다.")

    filters = [
        f"trpr_no = '{_escape_literal(transport_no)}'",
    ]

    if changed_from:
        filters.append(
            "ins_datetime >= "
            f"'{changed_from.strftime('%Y-%m-%d')}'"
        )

    frame = _fetch_view(
        view_path=HISTORY_VIEW_PATH,
        select_columns=HISTORY_SELECT_COLUMNS,
        filter_expr=" and ".join(filters),
        max_rows=max_rows,
        username=username,
        password=password,
    )

    frame = _prefer_exact_transport_codes(
        frame,
        cmpy_cd=cmpy_cd,
        plnt_cd=plnt_cd,
    )

    if frame.empty:
        return pd.DataFrame(columns=HISTORY_SELECT_COLUMNS)

    frame = frame.copy()
    frame["source_cmpy_cd"] = (
        frame.get("cmpy_cd", "")
    )
    frame["source_plnt_cd"] = (
        frame.get("plnt_cd", "")
    )

    requested_company = _normalized_code(cmpy_cd)
    requested_plant = _normalized_code(plnt_cd)

    if requested_company:
        frame["cmpy_cd"] = requested_company
    if requested_plant:
        frame["plnt_cd"] = requested_plant

    return _convert_date_columns(
        frame,
        HISTORY_DATE_COLUMNS,
    )



def fetch_bl_info_for_transport(
    trpr_no: str,
    *,
    cmpy_cd: Optional[str] = None,
    plnt_cd: Optional[str] = None,
    max_rows: int = 5_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> pd.DataFrame:
    """
    특정 B-LAP Transportation No.의 현재 Snapshot 행을 조회한다.

    원천 조회는 trpr_no만 사용한다. cmpy_cd/plnt_cd가 정확히
    일치하는 행이 있으면 우선 사용하되, 코드 불일치 때문에
    Snapshot 전체를 버리지는 않는다.
    """
    transport_no = _normalized_code(trpr_no)
    if not transport_no:
        raise ValueError("trpr_no는 필수입니다.")

    frame = _fetch_view(
        view_path=INFO_VIEW_PATH,
        select_columns=INFO_SELECT_COLUMNS,
        filter_expr=(
            f"trpr_no = '{_escape_literal(transport_no)}'"
        ),
        max_rows=max_rows,
        username=username,
        password=password,
    )

    frame = _prefer_exact_transport_codes(
        frame,
        cmpy_cd=cmpy_cd,
        plnt_cd=plnt_cd,
    )

    return _convert_date_columns(
        frame,
        INFO_DATE_COLUMNS,
    )
