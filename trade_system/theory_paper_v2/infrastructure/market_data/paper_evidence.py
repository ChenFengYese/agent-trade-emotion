"""Derive paper observations from already admitted asset data slices.

The adapter reuses ``AssetDataProfileService`` and therefore the existing
``FileRawCaptureStore`` behind it.  It owns no raw data and never accepts a
caller-provided price merely because the caller also supplied a known digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ...application.market_cycle.data_profiles import AssetDataProfileService
from ...domain.contracts.canonical import canonical_decimal, canonical_digest
from ...domain.market_cycle.data import AssetDataSliceV1
from ...domain.market_cycle.paper import (
    CarryAccrualV1,
    FundingCoverageAdvanceV1,
    InstrumentSpecV1,
    PaperMarketSliceV1,
)


class PaperMarketEvidenceConfigurationError(ValueError):
    """The paper evidence scope or an admitted slice is inconsistent."""


@dataclass(frozen=True, slots=True)
class PaperAssetEvidenceBinding:
    """Finite symbol/profile/cycle scope admitted for paper observation."""

    symbol: str
    profile_id: str
    cycle_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        cycles = tuple(self.cycle_ids)
        if (
            not isinstance(self.symbol, str)
            or not self.symbol
            or not isinstance(self.profile_id, str)
            or not self.profile_id
            or not cycles
            or len(cycles) != len(set(cycles))
            or any(not isinstance(item, str) or not item for item in cycles)
        ):
            raise PaperMarketEvidenceConfigurationError(
                "PAPER_MARKET_EVIDENCE_BINDING_INVALID"
            )
        object.__setattr__(self, "cycle_ids", cycles)


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _mapping(value: object, *, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PaperMarketEvidenceConfigurationError(code)
    return value


def _price_level(value: object, *, code: str) -> tuple[str, str]:
    row = _mapping(value, code=code)
    price = row.get("price")
    size = row.get("size_contracts")
    if not isinstance(price, str) or not isinstance(size, str):
        raise PaperMarketEvidenceConfigurationError(code)
    return canonical_decimal(Decimal(price)), canonical_decimal(Decimal(size))


def _positive_decimal(value: object, *, code: str) -> Decimal:
    if not isinstance(value, str):
        raise PaperMarketEvidenceConfigurationError(code)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise PaperMarketEvidenceConfigurationError(code) from exc
    if (
        not parsed.is_finite()
        or parsed <= 0
        or canonical_decimal(parsed) != value
    ):
        raise PaperMarketEvidenceConfigurationError(code)
    return parsed


def _observation_sha256(observation: Mapping[str, Any], *, code: str) -> str:
    digest = observation.get("raw_sha256")
    raw_ref = _mapping(observation.get("raw_ref"), code=code)
    if not isinstance(digest, str) or raw_ref.get("sha256") != digest:
        raise PaperMarketEvidenceConfigurationError(code)
    return digest


def _evidence_available_at(
    data_slice: AssetDataSliceV1,
    observation: Mapping[str, Any],
) -> str:
    """Return when both the raw observation and admitted slice were available."""

    observation_available_at = str(observation["available_at"])
    return max(
        (observation_available_at, data_slice.sealed_at),
        key=_moment,
    )


def derive_paper_market_slices(
    data_slice: AssetDataSliceV1,
) -> tuple[PaperMarketSliceV1, ...]:
    """Purely derive paper-visible MARK/QUOTE/TRADE/BAR observations.

    The function accepts only the already admitted immutable slice and performs
    no lookup, persistence, or network work.  Every returned observation keeps
    the exact raw digest carried by its source observation.
    """

    if not isinstance(data_slice, AssetDataSliceV1):
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_ADMITTED_ASSET_SLICE_REQUIRED"
        )
    symbol = data_slice.instrument_identity.venue_symbol
    derived: list[PaperMarketSliceV1] = []

    mark = data_slice.core_observations["mark_price"]
    mark_value = _positive_decimal(
        mark.get("value"), code="PAPER_MARK_PRICE_INVALID"
    )
    derived.append(
        PaperMarketSliceV1(
            symbol=symbol,
            observed_at=str(mark["observed_at"]),
            available_at=_evidence_available_at(data_slice, mark),
            source_sha256=_observation_sha256(
                mark, code="PAPER_MARK_RAW_BINDING_INVALID"
            ),
            granularity="MARK",
            # One provider-stamped point is temporally ordered.  This does not
            # claim a continuous path between separate MARK observations.
            path_status="ORDERED",
            mark=canonical_decimal(mark_value),
        )
    )

    book = data_slice.optional_observations.get("okx_order_book")
    if book is not None:
        book_value = _mapping(book.get("value"), code="PAPER_ORDER_BOOK_INVALID")
        bids = book_value.get("bids")
        asks = book_value.get("asks")
        if not isinstance(bids, (tuple, list)) or not bids or not isinstance(
            asks, (tuple, list)
        ) or not asks:
            raise PaperMarketEvidenceConfigurationError("PAPER_ORDER_BOOK_INVALID")
        bid_levels = [
            _price_level(item, code="PAPER_ORDER_BOOK_BID_INVALID") for item in bids
        ]
        ask_levels = [
            _price_level(item, code="PAPER_ORDER_BOOK_ASK_INVALID") for item in asks
        ]
        best_bid, bid_size = max(bid_levels, key=lambda item: Decimal(item[0]))
        best_ask, ask_size = min(ask_levels, key=lambda item: Decimal(item[0]))
        visible = canonical_decimal(min(Decimal(bid_size), Decimal(ask_size)))
        derived.append(
            PaperMarketSliceV1(
                symbol=symbol,
                observed_at=str(book["observed_at"]),
                available_at=_evidence_available_at(data_slice, book),
                source_sha256=_observation_sha256(
                    book, code="PAPER_ORDER_BOOK_RAW_BINDING_INVALID"
                ),
                granularity="QUOTE",
                path_status="UNORDERED",
                bid=best_bid,
                ask=best_ask,
                available_quantity=visible,
            )
        )

    trades = data_slice.optional_observations.get("okx_recent_trades")
    if trades is not None:
        rows = trades.get("value")
        if not isinstance(rows, (tuple, list)) or not rows:
            raise PaperMarketEvidenceConfigurationError("PAPER_RECENT_TRADES_INVALID")
        latest = max(
            (_mapping(item, code="PAPER_RECENT_TRADE_INVALID") for item in rows),
            key=lambda item: _moment(str(item.get("provider_as_of"))),
        )
        last = _positive_decimal(
            latest.get("price"), code="PAPER_RECENT_TRADE_PRICE_INVALID"
        )
        quantity = _positive_decimal(
            latest.get("size_contracts"), code="PAPER_RECENT_TRADE_SIZE_INVALID"
        )
        derived.append(
            PaperMarketSliceV1(
                symbol=symbol,
                observed_at=str(latest["provider_as_of"]),
                available_at=_evidence_available_at(data_slice, trades),
                source_sha256=_observation_sha256(
                    trades, code="PAPER_RECENT_TRADES_RAW_BINDING_INVALID"
                ),
                granularity="TRADE",
                path_status="UNORDERED",
                last=canonical_decimal(last),
                available_quantity=canonical_decimal(quantity),
            )
        )

    candles = data_slice.core_observations["closed_15m_bars"]
    rows = candles.get("value")
    if not isinstance(rows, (tuple, list)) or not rows:
        raise PaperMarketEvidenceConfigurationError("PAPER_CLOSED_BARS_INVALID")
    latest_bar = max(
        (_mapping(item, code="PAPER_CLOSED_BAR_INVALID") for item in rows),
        key=lambda item: _moment(str(item.get("closed_at"))),
    )
    close = _positive_decimal(
        latest_bar.get("close"), code="PAPER_CLOSED_BAR_CLOSE_INVALID"
    )
    low = _positive_decimal(
        latest_bar.get("low"), code="PAPER_CLOSED_BAR_LOW_INVALID"
    )
    high = _positive_decimal(
        latest_bar.get("high"), code="PAPER_CLOSED_BAR_HIGH_INVALID"
    )
    derived.append(
        PaperMarketSliceV1(
            symbol=symbol,
            observed_at=str(latest_bar["closed_at"]),
            available_at=_evidence_available_at(data_slice, candles),
            source_sha256=_observation_sha256(
                candles, code="PAPER_CLOSED_BARS_RAW_BINDING_INVALID"
            ),
            granularity="BAR",
            path_status="UNORDERED",
            last=canonical_decimal(close),
            low=canonical_decimal(low),
            high=canonical_decimal(high),
        )
    )
    return tuple(
        sorted(
            derived,
            key=lambda item: (
                _moment(item.available_at),
                _moment(item.observed_at),
                item.granularity,
                item.source_sha256,
            ),
        )
    )


def _derive_linear_perp_instrument_spec(
    data_slice: AssetDataSliceV1,
    *,
    symbol: str,
    account_mode: str,
) -> InstrumentSpecV1:
    if not isinstance(data_slice, AssetDataSliceV1):
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_ADMITTED_ASSET_SLICE_REQUIRED"
        )
    if account_mode != "LINEAR_PERP":
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_INSTRUMENT_ACCOUNT_MODE_UNSUPPORTED"
        )
    identity = data_slice.instrument_identity
    if (
        identity.venue_symbol != symbol
        or identity.market_type != "SWAP"
        or identity.contract_semantics != "LINEAR_PERPETUAL_SWAP"
        or identity.quote_asset != identity.settle_asset
        or identity.status != "ACTIVE"
    ):
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_INSTRUMENT_IDENTITY_INVALID"
        )

    observation = data_slice.core_observations["instrument"]
    raw_sha256 = _observation_sha256(
        observation, code="PAPER_INSTRUMENT_RAW_BINDING_INVALID"
    )
    if (
        raw_sha256 != identity.source_ref.sha256
        or raw_sha256 not in {item.sha256 for item in data_slice.raw_refs}
    ):
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_INSTRUMENT_RAW_BINDING_INVALID"
        )
    value = _mapping(
        observation.get("value"), code="PAPER_INSTRUMENT_OBSERVATION_INVALID"
    )
    if (
        value.get("instrument_id") != symbol
        or value.get("instrument_type") != "SWAP"
        or value.get("contract_family") != "linear"
        or value.get("base_currency") != identity.base_asset
        or value.get("quote_currency") != identity.quote_asset
        or value.get("settlement_currency") != identity.settle_asset
        or value.get("contract_value_currency") != identity.base_asset
    ):
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_INSTRUMENT_OBSERVATION_IDENTITY_MISMATCH"
        )
    contract_value = _positive_decimal(
        value.get("contract_value"), code="PAPER_CONTRACT_VALUE_INVALID"
    )
    provider_multiplier = _positive_decimal(
        value.get("contract_multiplier"), code="PAPER_CONTRACT_MULTIPLIER_INVALID"
    )
    contract_value_text = canonical_decimal(contract_value)
    provider_multiplier_text = canonical_decimal(provider_multiplier)
    expected_basis = (
        f"{contract_value_text} {identity.base_asset} PER_CONTRACT X "
        f"{provider_multiplier_text}"
    )
    if identity.quantity_basis != expected_basis:
        raise PaperMarketEvidenceConfigurationError(
            "PAPER_INSTRUMENT_QUANTITY_BASIS_MISMATCH"
        )
    effective_multiplier = canonical_decimal(contract_value * provider_multiplier)
    binding = {
        "symbol": symbol,
        "account_mode": account_mode,
        "quote_currency": identity.settle_asset,
        "contract_value": contract_value_text,
        "provider_contract_multiplier": provider_multiplier_text,
        "effective_contract_multiplier": effective_multiplier,
        "quantity_basis": "CONTRACTS",
        "source_sha256": raw_sha256,
    }
    return InstrumentSpecV1(
        instrument_spec_id=f"paper-instrument-{canonical_digest(binding)[:32]}",
        symbol=symbol,
        account_mode=account_mode,
        quote_currency=identity.settle_asset,
        contract_multiplier=effective_multiplier,
        quantity_basis="CONTRACTS",
        parameter_status="OBSERVED_RAW_BOUND",
        parameter_source_sha256=raw_sha256,
    )


class AdmittedAssetSlicePaperMarketEvidence:
    """Implement ``PaperMarketEvidencePort`` by exact slice derivation.

    ``derive_slices`` is the intended producer API.  ``verifies_market_slice``
    independently replays the finite admitted cycle set and accepts only a
    value exactly equal to one of those derived immutable observations.
    """

    def __init__(
        self,
        *,
        profiles: AssetDataProfileService,
        bindings: Sequence[PaperAssetEvidenceBinding],
    ) -> None:
        if not isinstance(profiles, AssetDataProfileService):
            raise PaperMarketEvidenceConfigurationError(
                "PAPER_MARKET_DATA_PROFILE_SERVICE_INVALID"
            )
        supplied = tuple(bindings)
        if (
            not supplied
            or not all(isinstance(item, PaperAssetEvidenceBinding) for item in supplied)
            or len({item.symbol for item in supplied}) != len(supplied)
        ):
            raise PaperMarketEvidenceConfigurationError(
                "PAPER_MARKET_EVIDENCE_BINDINGS_INVALID"
            )
        for item in supplied:
            profile = profiles.require_profile(item.profile_id)
            if profile.instrument_id != item.symbol:
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_MARKET_EVIDENCE_PROFILE_SYMBOL_MISMATCH"
                )
        self._profiles = profiles
        self._bindings = MappingProxyType({item.symbol: item for item in supplied})

    def derive_slices(self, symbol: str) -> tuple[PaperMarketSliceV1, ...]:
        binding = self._bindings.get(symbol)
        if binding is None:
            return ()
        result: list[PaperMarketSliceV1] = []
        for cycle_id in binding.cycle_ids:
            replay = self._profiles.replay(binding.profile_id, cycle_id=cycle_id)
            if replay.status != "ADMITTED" or replay.data_slice is None:
                continue
            if replay.data_slice.instrument_identity.venue_symbol != symbol:
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_MARKET_EVIDENCE_SLICE_SYMBOL_MISMATCH"
                )
            result.extend(derive_paper_market_slices(replay.data_slice))
        # A set removes duplicate views without creating another durable index.
        unique = set(result)
        return tuple(
            sorted(
                unique,
                key=lambda item: (
                    _moment(item.available_at),
                    _moment(item.observed_at),
                    item.granularity,
                    item.source_sha256,
                ),
            )
        )

    def latest_order_book_slice(self, symbol: str) -> PaperMarketSliceV1 | None:
        quotes = [
            item for item in self.derive_slices(symbol) if item.granularity == "QUOTE"
        ]
        return None if not quotes else quotes[-1]

    def latest_mark_slice(self, symbol: str) -> PaperMarketSliceV1 | None:
        marks = [item for item in self.derive_slices(symbol) if item.granularity == "MARK"]
        return None if not marks else marks[-1]

    def latest_instrument_spec(
        self,
        symbol: str,
        account_mode: str,
        *,
        available_by: str | None = None,
    ) -> InstrumentSpecV1 | None:
        """Return newest raw-bound product economics available by the cutoff."""

        if account_mode != "LINEAR_PERP":
            raise PaperMarketEvidenceConfigurationError(
                "PAPER_INSTRUMENT_ACCOUNT_MODE_UNSUPPORTED"
            )
        binding = self._bindings.get(symbol)
        if binding is None:
            return None
        cutoff = None if available_by is None else _moment(available_by)
        candidates: list[tuple[datetime, datetime, InstrumentSpecV1]] = []
        for cycle_id in binding.cycle_ids:
            replay = self._profiles.replay(binding.profile_id, cycle_id=cycle_id)
            if replay.status != "ADMITTED" or replay.data_slice is None:
                continue
            observation = replay.data_slice.core_observations["instrument"]
            observation_available_at = _moment(str(observation["available_at"]))
            slice_sealed_at = _moment(replay.data_slice.sealed_at)
            if cutoff is not None:
                if observation_available_at > cutoff or slice_sealed_at > cutoff:
                    continue
            candidates.append(
                (
                    max(observation_available_at, slice_sealed_at),
                    _moment(str(observation["observed_at"])),
                    _derive_linear_perp_instrument_spec(
                        replay.data_slice,
                        symbol=symbol,
                        account_mode=account_mode,
                    ),
                )
            )
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[0], item[1]))[2]

    def verifies_instrument_spec(
        self,
        instrument_spec: InstrumentSpecV1,
        *,
        available_by: str,
    ) -> bool:
        """Verify raw product economics while allowing an explicit risk overlay."""

        if not isinstance(instrument_spec, InstrumentSpecV1):
            return False
        expected = self.latest_instrument_spec(
            instrument_spec.symbol,
            instrument_spec.account_mode,
            available_by=available_by,
        )
        if expected is None:
            return False
        raw_bound_fields = (
            "instrument_spec_id",
            "symbol",
            "account_mode",
            "quote_currency",
            "contract_multiplier",
            "quantity_basis",
            "parameter_status",
            "parameter_source_sha256",
        )
        return all(
            getattr(instrument_spec, field) == getattr(expected, field)
            for field in raw_bound_fields
        )

    def verifies_carry_accrual(self, accrual: CarryAccrualV1) -> bool:
        """Verify only raw-observed funding inputs; application owns amount math.

        A current MARK is a valid funding reference only when its provider
        timestamp exactly equals the realized funding record's effective time.
        Merely capturing both values in one later cycle is not treated as a
        historical mark-at-funding-time observation.
        """

        if not isinstance(accrual, CarryAccrualV1):
            return False
        if accrual.status in {"UNKNOWN", "NOT_APPLICABLE"}:
            return True
        if accrual.status != "OBSERVED" or accrual.kind != "FUNDING":
            return False
        # One matched history row proves one funding point, not that no
        # settlement was missed across a wider interval.  COMPLETE is reserved
        # for a later scheduler that enumerates and books every expected event.
        if (
            accrual.coverage_status != "PARTIAL"
            or accrual.coverage_start_at != accrual.effective_at
            or accrual.coverage_end_at != accrual.effective_at
        ):
            return False
        binding = self._bindings.get(accrual.symbol)
        if binding is None:
            return False
        for cycle_id in binding.cycle_ids:
            replay = self._profiles.replay(binding.profile_id, cycle_id=cycle_id)
            if replay.status != "ADMITTED" or replay.data_slice is None:
                continue
            data_slice = replay.data_slice
            if data_slice.instrument_identity.venue_symbol != accrual.symbol:
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_CARRY_SLICE_SYMBOL_MISMATCH"
                )
            funding = data_slice.optional_observations.get(
                "okx_funding_rate_history"
            )
            if funding is None:
                continue
            rows = funding.get("value")
            if not isinstance(rows, (tuple, list)) or not rows:
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_FUNDING_HISTORY_INVALID"
                )
            funding_sha256 = _observation_sha256(
                funding, code="PAPER_FUNDING_RAW_BINDING_INVALID"
            )
            model = accrual.settlement_model
            if model is None:
                price_observation = data_slice.core_observations["mark_price"]
                price_sha256 = _observation_sha256(
                    price_observation, code="PAPER_MARK_RAW_BINDING_INVALID"
                )
                price_available_at = str(price_observation.get("available_at"))
                reference_price = canonical_decimal(
                    _positive_decimal(
                        price_observation.get("value"),
                        code="PAPER_MARK_PRICE_INVALID",
                    )
                )
                price_observed_at = str(price_observation.get("observed_at"))
            else:
                price_observation = data_slice.core_observations[
                    "closed_15m_bars"
                ]
                price_sha256 = _observation_sha256(
                    price_observation, code="PAPER_CANDLES_RAW_BINDING_INVALID"
                )
                price_available_at = str(price_observation.get("available_at"))
                bar_rows = price_observation.get("value")
                if not isinstance(bar_rows, (tuple, list)) or not bar_rows:
                    raise PaperMarketEvidenceConfigurationError(
                        "PAPER_CANDLES_INVALID"
                    )
                eligible = [
                    _mapping(row, code="PAPER_CANDLE_INVALID")
                    for row in bar_rows
                    if isinstance(row, Mapping)
                    and isinstance(row.get("closed_at"), str)
                    and _moment(str(row["closed_at"]))
                    <= _moment(accrual.effective_at)
                ]
                if not eligible:
                    continue
                proxy = max(
                    eligible, key=lambda row: _moment(str(row["closed_at"]))
                )
                price_observed_at = str(proxy["closed_at"])
                reference_price = canonical_decimal(
                    _positive_decimal(
                        proxy.get("close"), code="PAPER_CANDLE_CLOSE_INVALID"
                    )
                )
                if accrual.price_proxy_observed_at != price_observed_at:
                    continue
            if _moment(accrual.available_at) < max(
                _moment(str(funding.get("available_at"))),
                _moment(price_available_at),
                _moment(data_slice.sealed_at),
            ):
                continue
            if not (
                _moment(accrual.coverage_start_at)
                <= _moment(accrual.effective_at)
                <= _moment(accrual.coverage_end_at)
                <= _moment(str(funding.get("available_at")))
            ):
                continue
            for raw_row in rows:
                row = _mapping(raw_row, code="PAPER_FUNDING_RECORD_INVALID")
                effective_at = row.get("provider_as_of")
                rate = row.get("realized_rate", row.get("funding_rate"))
                if (
                    row.get("instrument_id") == accrual.symbol
                    and isinstance(effective_at, str)
                    and accrual.effective_at == effective_at
                    and accrual.rate == rate
                    and accrual.rate_source_sha256 == funding_sha256
                    and accrual.reference_price == reference_price
                    and accrual.price_source_sha256 == price_sha256
                    and (
                        model is not None
                        or effective_at == price_observed_at
                    )
                ):
                    return True
        return False

    def verifies_funding_coverage(
        self, advance: FundingCoverageAdvanceV1
    ) -> bool:
        """Prove a COMPLETE interval from one after-window official history.

        The history must contain strict rows on both sides of the window.  This
        makes a ten-row truncation visible instead of interpreting absence as
        zero.  Closed 15-minute bars supply the frozen, pre-event price proxy.
        """

        if not isinstance(advance, FundingCoverageAdvanceV1):
            return False
        binding = self._bindings.get(advance.symbol)
        if binding is None:
            return False
        start = _moment(advance.coverage_start_at)
        end = _moment(advance.coverage_end_at)
        for cycle_id in binding.cycle_ids:
            replay = self._profiles.replay(binding.profile_id, cycle_id=cycle_id)
            if replay.status != "ADMITTED" or replay.data_slice is None:
                continue
            data_slice = replay.data_slice
            funding = data_slice.optional_observations.get(
                "okx_funding_rate_history"
            )
            if funding is None:
                continue
            bars = data_slice.core_observations["closed_15m_bars"]
            funding_sha256 = _observation_sha256(
                funding, code="PAPER_FUNDING_RAW_BINDING_INVALID"
            )
            bars_sha256 = _observation_sha256(
                bars, code="PAPER_CANDLES_RAW_BINDING_INVALID"
            )
            if (
                funding_sha256 != advance.funding_history_source_sha256
                or bars_sha256 != advance.price_proxy_source_sha256
                or _moment(advance.available_at)
                < max(
                    _moment(str(funding.get("available_at"))),
                    _moment(str(bars.get("available_at"))),
                    _moment(data_slice.sealed_at),
                )
                or _moment(str(funding.get("available_at"))) <= end
            ):
                continue
            raw_rows = funding.get("value")
            if not isinstance(raw_rows, (tuple, list)) or not raw_rows:
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_FUNDING_HISTORY_INVALID"
                )
            rows = tuple(
                _mapping(row, code="PAPER_FUNDING_RECORD_INVALID")
                for row in raw_rows
            )
            if any(row.get("instrument_id") != advance.symbol for row in rows):
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_FUNDING_RECORD_SYMBOL_MISMATCH"
                )
            times = tuple(
                str(row["provider_as_of"])
                for row in rows
                if isinstance(row.get("provider_as_of"), str)
            )
            if len(times) != len(rows) or len(times) != len(set(times)):
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_FUNDING_RECORD_TIME_INVALID"
                )
            before = tuple(value for value in times if _moment(value) < start)
            after = tuple(value for value in times if _moment(value) > end)
            if not before or not after:
                continue
            nearest_before = max(before, key=_moment)
            nearest_after = min(after, key=_moment)
            inside = tuple(
                sorted(
                    (
                        value
                        for value in times
                        if start <= _moment(value) <= end
                    ),
                    key=_moment,
                )
            )
            if (
                nearest_before != advance.history_boundary_before_at
                or nearest_after != advance.history_boundary_after_at
                or inside != advance.event_effective_ats
            ):
                continue
            raw_bar_rows = bars.get("value")
            if not isinstance(raw_bar_rows, (tuple, list)) or not raw_bar_rows:
                raise PaperMarketEvidenceConfigurationError(
                    "PAPER_CANDLES_INVALID"
                )
            closed = tuple(
                _mapping(row, code="PAPER_CANDLE_INVALID")
                for row in raw_bar_rows
            )
            if any(
                not any(
                    isinstance(row.get("closed_at"), str)
                    and _moment(str(row["closed_at"])) <= _moment(event_at)
                    for row in closed
                )
                for event_at in inside
            ):
                continue
            return True
        return False

    def verifies_market_slice(self, market: PaperMarketSliceV1) -> bool:
        if not isinstance(market, PaperMarketSliceV1):
            return False
        return market in self.derive_slices(market.symbol)

    @staticmethod
    def _derive_one(data_slice: AssetDataSliceV1) -> tuple[PaperMarketSliceV1, ...]:
        return derive_paper_market_slices(data_slice)


__all__ = [
    "AdmittedAssetSlicePaperMarketEvidence",
    "PaperAssetEvidenceBinding",
    "PaperMarketEvidenceConfigurationError",
    "derive_paper_market_slices",
]
