"""Cross-product identity graph for the initially discussed SNDK surfaces.

Per-slice venue identity remains owned by ``data.InstrumentIdentityV1``.  This
module only records relationships between distinct products and must never be
used as an admitted asset-data slice by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any


class InstrumentIdentityError(ValueError):
    """An instrument node or relationship is ambiguous or falsely conflated."""


_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise InstrumentIdentityError(f"{field} must be a safe identifier")
    return value


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise InstrumentIdentityError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InstrumentIdentityError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InstrumentIdentityError(f"{field} must include an explicit UTC offset")
    return value


@dataclass(frozen=True, slots=True)
class ProductIdentityNodeV1:
    product_id: str
    symbol: str
    product_type: str
    issuer_or_venue: str
    quote_currency: str | None
    settlement_currency: str | None
    contract_semantics: str
    status: str
    discovered_at: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _identifier(self.product_id, field="product_id"))
        object.__setattr__(self, "symbol", _identifier(self.symbol, field="symbol"))
        if self.product_type not in {
            "EQUITY",
            "TOKENIZED_EQUITY",
            "SPOT_TOKEN",
            "LINEAR_PERPETUAL",
        }:
            raise InstrumentIdentityError("product_type is unsupported")
        object.__setattr__(self, "issuer_or_venue", _identifier(self.issuer_or_venue, field="issuer_or_venue"))
        for field_name in ("quote_currency", "settlement_currency"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _identifier(value, field=field_name))
        if not isinstance(self.contract_semantics, str) or not self.contract_semantics.strip():
            raise InstrumentIdentityError("contract_semantics must be non-empty")
        if self.status not in {"ADMITTED", "NOT_ADMITTED", "UNKNOWN"}:
            raise InstrumentIdentityError("status is unsupported")
        object.__setattr__(self, "discovered_at", _timestamp(self.discovered_at, field="discovered_at"))
        object.__setattr__(self, "source_id", _identifier(self.source_id, field="source_id"))

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ProductRelationshipV1:
    source_product_id: str
    target_product_id: str
    relationship: str
    admission_status: str
    evidence: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_product_id",
            _identifier(self.source_product_id, field="source_product_id"),
        )
        object.__setattr__(
            self,
            "target_product_id",
            _identifier(self.target_product_id, field="target_product_id"),
        )
        if self.source_product_id == self.target_product_id:
            raise InstrumentIdentityError("relationship must connect distinct products")
        if self.relationship not in {
            "REFERENCES_UNDERLYING",
            "VENUE_LISTING_OF",
            "ECONOMIC_PROXY_ONLY",
            "IDENTITY_NOT_ESTABLISHED",
        }:
            raise InstrumentIdentityError("relationship is unsupported")
        if self.admission_status not in {"ADMITTED", "NOT_ADMITTED", "UNKNOWN"}:
            raise InstrumentIdentityError("admission_status is unsupported")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise InstrumentIdentityError("evidence must be non-empty")

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ProductIdentityGraphV1:
    graph_id: str
    nodes: tuple[ProductIdentityNodeV1, ...]
    relationships: tuple[ProductRelationshipV1, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "graph_id", _identifier(self.graph_id, field="graph_id"))
        node_ids = {node.product_id for node in self.nodes}
        if len(node_ids) != len(self.nodes) or not self.nodes:
            raise InstrumentIdentityError("nodes must be non-empty and unique")
        for relationship in self.relationships:
            if (
                relationship.source_product_id not in node_ids
                or relationship.target_product_id not in node_ids
            ):
                raise InstrumentIdentityError("relationship references an unknown product")

    def node(self, product_id: str) -> ProductIdentityNodeV1:
        try:
            return next(node for node in self.nodes if node.product_id == product_id)
        except StopIteration as exc:
            raise InstrumentIdentityError("product is absent from the graph") from exc

    def require_same_product(self, left_product_id: str, right_product_id: str) -> None:
        if left_product_id == right_product_id:
            self.node(left_product_id)
            return
        raise InstrumentIdentityError("distinct product identities must not be conflated")

    def admitted_market(self, product_id: str) -> ProductIdentityNodeV1:
        node = self.node(product_id)
        if node.status != "ADMITTED" or node.product_type not in {
            "SPOT_TOKEN",
            "LINEAR_PERPETUAL",
        }:
            raise InstrumentIdentityError("product is not an admitted venue market")
        return node


def sndk_identity_graph(
    *,
    discovered_at: str,
    include_okx_swap: bool = True,
) -> ProductIdentityGraphV1:
    """Return strict identities; it does not claim SNDK-USDT-SWAP equals SNDKx."""

    nodes = (
        ProductIdentityNodeV1(
            product_id="equity:nasdaq:SNDK",
            symbol="SNDK",
            product_type="EQUITY",
            issuer_or_venue="NASDAQ",
            quote_currency="USD",
            settlement_currency="USD",
            contract_semantics="Sandisk Corporation common equity; CIK 0002023554",
            status="ADMITTED",
            discovered_at=discovered_at,
            source_id="sec.company.identity",
        ),
        ProductIdentityNodeV1(
            product_id="token:backed:SNDKx",
            symbol="SNDKx",
            product_type="TOKENIZED_EQUITY",
            issuer_or_venue="BackedAssetsJE",
            quote_currency=None,
            settlement_currency=None,
            contract_semantics="Backed-issued tokenized product; ISIN CH1500008748; underlying ISIN US80004C2008",
            status="ADMITTED",
            discovered_at=discovered_at,
            source_id="backed.token.identity",
        ),
        ProductIdentityNodeV1(
            product_id="spot:kraken-international:SNDKx-USD",
            symbol="SNDKx-USD",
            product_type="SPOT_TOKEN",
            issuer_or_venue="KrakenInternational",
            quote_currency="USD",
            settlement_currency="USD",
            contract_semantics="Kraken international tokenized-asset spot market",
            status="ADMITTED",
            discovered_at=discovered_at,
            source_id="kraken.assetpairs",
        ),
        ProductIdentityNodeV1(
            product_id="perp:okx:SNDK-USDT-SWAP",
            symbol="SNDK-USDT-SWAP",
            product_type="LINEAR_PERPETUAL",
            issuer_or_venue="OKX",
            quote_currency="USDT",
            settlement_currency="USDT",
            contract_semantics="Linear USDT-settled perpetual; ctVal=1 SNDK at discovery",
            status="ADMITTED" if include_okx_swap else "UNKNOWN",
            discovered_at=discovered_at,
            source_id="okx.instrument",
        ),
    )
    relationships = (
        ProductRelationshipV1(
            source_product_id="token:backed:SNDKx",
            target_product_id="equity:nasdaq:SNDK",
            relationship="REFERENCES_UNDERLYING",
            admission_status="ADMITTED",
            evidence="Backed public identity metadata supplies underlyingSymbol SNDK and underlyingIsin US80004C2008.",
        ),
        ProductRelationshipV1(
            source_product_id="spot:kraken-international:SNDKx-USD",
            target_product_id="token:backed:SNDKx",
            relationship="VENUE_LISTING_OF",
            admission_status="ADMITTED",
            evidence="Kraken AssetPairs classifies base SNDKx as tokenized_asset and reports the market online.",
        ),
        ProductRelationshipV1(
            source_product_id="perp:okx:SNDK-USDT-SWAP",
            target_product_id="token:backed:SNDKx",
            relationship="IDENTITY_NOT_ESTABLISHED",
            admission_status="NOT_ADMITTED",
            evidence="An OKX instrument with base label SNDK is observable, but issuer, multiplier, backing and basis identity to Backed SNDKx are not established.",
        ),
        ProductRelationshipV1(
            source_product_id="perp:okx:SNDK-USDT-SWAP",
            target_product_id="equity:nasdaq:SNDK",
            relationship="ECONOMIC_PROXY_ONLY",
            admission_status="UNKNOWN",
            evidence="The derivative may economically reference SNDK, but the captured public identity evidence does not establish a one-to-one product identity or basis model.",
        ),
    )
    return ProductIdentityGraphV1(
        graph_id="sndk-market-surfaces-v1",
        nodes=nodes,
        relationships=relationships,
    )
