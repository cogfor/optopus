#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug  5 07:21:38 2018

@author: ilia
"""
import datetime
import logging
from typing import List, Dict, Tuple

from ib_insync.contract import Index as IBIndex, Option as IBOption, Stock as IBStock
from ib_insync.ib import IB, Contract
from ib_insync.objects import (
    AccountValue,
    ComboLeg,
)
from ib_insync.order import Trade as IBTrade, LimitOrder

from optopus.asset import AssetId, Asset, Current, History, Bar, Stock, ETF, Index
from optopus.common import AssetType, AssetDefinition, Currency
from optopus.data_manager import DataAdapter
from optopus.data_objects import Position, OwnershipType, Account, OrderStatus, Trade
from optopus.option import Option, OptionId, RightType
from optopus.settings import CURRENCY, HISTORICAL_YEARS
from optopus.strategy import StrategyType, Strategy
from optopus.utils import parse_ib_date, format_ib_date


class IBBrokerAdapter:
    """Class implementing the Interactive Brokers interface"""

    def __init__(self, ib: IB, host: str, port: int, client: int) -> None:
        self._broker = ib
        self._host = host
        self._port = port
        self._client = client
        self._translator = IBTranslator()
        self._data_adapter = IBDataAdapter(self._broker, self._translator)

        self.emit_order_status = None
        self._broker.orderStatusEvent += self._onOrderStatusEvent

    def connect(self) -> None:
        self._broker.connect(self._host, self._port, self._client)

    def disconnect(self) -> None:
        self._broker.disconnect()

    def sleep(self, time: float) -> None:
        self._broker.sleep(time)

    def _onOrderStatusEvent(self, trade: IBTrade):
        self.emit_order_status(self._translator.translate_trade(trade))

    def _reverse_ownership(sefl, ownership):
        return "BUY" if ownership == "SELL" else "SELL"

    def open_strategy(self, strategy: Strategy) -> None:
        """Place a new strategy at the market
        """

        ownership = "BUY" if strategy.ownership == OwnershipType.Buyer else "SELL"
        reverse_ownership = "BUY" if ownership == "SELL" else "SELL"

        contract = Contract()
        contract.symbol = strategy.code
        contract.secType = "BAG"
        contract.exchange = "SMART"
        contract.currency = strategy.currency.value
        order_comboLegs = []
        tp_sl_comboLegs = []

        for leg in strategy.legs.values():
            leg_order = ComboLeg()
            leg_order.conId = leg.option.contract.conId
            leg_order.ratio = leg.ratio
            leg_order.action = "BUY" if leg.ownership == OwnershipType.Buyer else "SELL"
            # contract.comboLegs.append(leg_order)
            order_comboLegs.append(leg_order)

        for leg in strategy.legs.values():
            leg_tp_sl = ComboLeg()
            leg_tp_sl.conId = leg.option.contract.conId
            leg_tp_sl.ratio = leg.ratio
            leg_tp_sl.action = (
                "SELL" if leg.ownership == OwnershipType.Buyer else "BUY"
            )  # reverse
            # contract.comboLegs.append(leg_order)
            tp_sl_comboLegs.append(leg_tp_sl)

        contract.comboLegs = order_comboLegs
        order = LimitOrder(
            action="BUY" if strategy.ownership == OwnershipType.Buyer else "SELL",
            totalQuantity=strategy.quantity,
            lmtPrice=strategy.entry_price,
            orderRef=strategy.strategy_id,
            orderId=self._broker.client.getReqId(),
            tif="GTC",
            transmit=True,
        )  # Must be False
        print("ORDER SENDED")
        self._broker.placeOrder(contract, order)

        # contract.comboLegs = tp_sl_comboLegs

        # print('take_profit_order', strategy.take_profit_price)
        take_profit = LimitOrder(
            action="SELL"
            if strategy.ownership == OwnershipType.Buyer
            else "BUY",  # reverse
            totalQuantity=strategy.quantity,
            lmtPrice=strategy.take_profit_price,
            # lmtPrice = -0.1,
            orderRef=strategy.strategy_id + "_TP",
            orderId=self._broker.client.getReqId(),
            tif="GTC",
            transmit=True,
            parentId=order.orderId,
        )
        self._broker.placeOrder(contract, take_profit)


class IBTranslator:
    """Translate the IB tags and values to Ocptopus"""

    def __init__(self) -> None:
        self._sectype_translation = {
            "STK": AssetType.Stock,
            "ETF": AssetType.ETF,
            "OPT": AssetType.Option,
            "FUT": AssetType.Future,
            "CASH": AssetType.Future,
            "IND": AssetType.Index,
            "CFD": AssetType.CFD,
            "BOND": AssetType.Bond,
            "CMDTY": AssetType.Commodity,
            "FOP": AssetType.FuturesOption,
            "FUND": AssetType.MutualFund,
            "IOPT": AssetType.Warrant,
        }

        self._right_translation = {"C": RightType.Call, "P": RightType.Put}

        self._order_status_translation = {
            "ApiPending": OrderStatus.APIPending,
            "PendingSubmit": OrderStatus.PendingSubmit,
            "PendingCancel": OrderStatus.PendingCancel,
            "PreSubmitted": OrderStatus.PreSubmitted,
            "Submitted": OrderStatus.Submitted,
            "ApiCancelled": OrderStatus.APICancelled,
            "Cancelled": OrderStatus.Cancelled,
            "Filled": OrderStatus.Filled,
            "Inactive": OrderStatus.Inactive,
        }

        self._ownership_translation = {
            "BUY": OwnershipType.Buyer,
            "SELL": OwnershipType.Seller,
        }

        self._strategy_translation = {
            "SP": StrategyType.ShortPut,
            "SPVS": StrategyType.ShortPutVerticalSpread,
            "SCVS": StrategyType.ShortCallVerticalSpread,
        }

        self._currency_translation = {
            "USD": Currency.USDollar,
            "EUR": Currency.Euro
        }

    def translate_account(self, values: List[AccountValue]) -> Account:
        account = Account()
        for v in values:
            if v.currency == CURRENCY.value:
                if v.tag == "AvailableFunds":
                    account.funds = float(v.value)
                elif v.tag == "BuyingPower":
                    account.buying_power = float(v.value)
                elif v.tag == "TotalCashValue":
                    account.cash = float(v.value)
                elif v.tag == "DayTradesRemaining":
                    account.max_day_trades = float(v.value)
                elif v.tag == "NetLiquidation":
                    account.net_liquidation = float(v.value)
                elif v.tag == "InitMarginReq":
                    account.initial_margin = float(v.value)
                elif v.tag == "MaintMarginReq":
                    account.maintenance_margin = float(v.value)
                elif v.tag == "ExcessLiquidity":
                    account.excess_liquidity = float(v.value)
                elif v.tag == "Cushion":
                    account.cushion = float(v.value)
                elif v.tag == "GrossPositionValue":
                    account.gross_position_value = float(v.value)
                elif v.tag == "EquityWithLoanValue":
                    account.equity_with_loan = float(v.value)
                elif v.tag == "SMA":
                    account.SMA = float(v.value)
        return account

    def translate_position(self, item: Position) -> Position:
        code = item.contract.symbol
        asset_type = self._sectype_translation[item.contract.secType]

        if item.position > 0:
            ownership = OwnershipType.Buyer
        elif item.position < 0:
            ownership = OwnershipType.Seller
        else:
            ownership = None

        expiration = item.contract.lastTradeDateOrContractMonth
        if expiration:
            expiration = parse_ib_date(expiration)
        else:
            expiration = None

        right = item.contract.right
        if right:
            right = self._right_translation[right]
        else:
            right = None

        position = PositionData(
            code=code,
            asset_type=asset_type,
            expiration=expiration,
            ownership=ownership,
            quantity=abs(item.position),
            strike=item.contract.strike,
            right=right,
            average_cost=item.avgCost,
        )
        return position

    def translate_trade(self, item: IBTrade) -> Trade:

        # print(item)

        order_id = item.order.orderRef
        status = self._order_status_translation[item.orderStatus.status]
        remaining = item.orderStatus.remaining
        try:
            commission = item.commissionReport.commission
        except AttributeError as e:
            commission = None

        trade = Trade(
            order_id=order_id, status=status, remaining=remaining, commission=commission
        )
        return trade

    def translate_bars(self, code: str, ibbars: list) -> list:
        bars = []
        for ibb in ibbars:
            b = Bar(
                time=ibb.date,
                open=ibb.open,
                high=ibb.high,
                low=ibb.low,
                close=ibb.close,
                average=ibb.average,
                volume=ibb.volume,
                count=ibb.barCount,
            )
            bars.append(b)
        return tuple(bars)


class IBDataAdapter(DataAdapter):
    def __init__(self, broker: IB, translator: IBTranslator) -> None:
        self._broker = broker
        self._translator = translator
        self._log = logging.getLogger(__name__)

    def get_account_values(self):
        values = self._broker.accountValues()
        account = self._translator.translate_account(values)
        return account

    def get_positions(self) -> Dict[str, Position]:
        positions = self._broker.positions()
        positions_data = {}
        for p in positions:
            pd = self._translator.translate_position(p)
            positions_data[pd.position_id] = pd
        return positions_data

    def create_assets(self, watchlist: Tuple[AssetDefinition]) -> List[Asset]:
        watchlist_dict = {i.code: i for i in watchlist}
        contracts = []
        for item in watchlist:
            if item.asset_type == AssetType.Stock or item.asset_type == AssetType.ETF:
                contracts.append(
                    IBStock(item.code, exchange="SMART", currency=item.currency.value)
                )
            if item.asset_type == AssetType.Index:
                contracts.append(
                    IBIndex(item.code, exchange=item.exchange)
                )
        # TODO: Remove the limit
        # It works if len(contracts) < 50. IB limit.
        q_contracts = self._broker.qualifyContracts(*contracts)
        if len(q_contracts) == len(watchlist):
            assets = {}
            for qc in q_contracts:
                id = AssetId(
                    code=qc.symbol,
                    asset_type=watchlist_dict[qc.symbol].asset_type,
                    currency=self._translator._currency_translation[qc.currency],
                    contract=qc,
                )
                if id.asset_type == AssetType.Stock:
                    assets[id.code] = Stock(id)
                elif id.asset_type == AssetType.ETF:
                    assets[id.code] = ETF(id)
                elif id.asset_type == AssetType.Index:
                    assets[id.code] = Index(id)


        else:
            raise ValueError("Error: ambiguous contracts")

        return assets

    def update_assets(self, assets: Dict[str, Asset]) -> Dict[str, Current]:
        contracts = [a.id.contract for a in assets.values()]
        tickers = self._broker.reqTickers(*contracts)
        current_values = {}
        for t in tickers:
            c = Current(
                high=t.high,
                low=t.low,
                close=t.close,
                bid=t.bid,
                bid_size=t.bidSize,
                ask=t.ask,
                ask_size=t.askSize,
                last=t.last,
                last_size=t.lastSize,
                volume=t.volume,
                time=t.time,
            )
            current_values[t.contract.symbol] = c
        return current_values

    def get_price_history(self, a: Asset) -> None:
        bars = self._broker.reqHistoricalData(
            a.id.contract,
            endDateTime="",
            durationStr=str(HISTORICAL_YEARS) + " Y",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        return History(self._translator.translate_bars(a.id.code, bars))

    def get_iv_history(self, a: Asset) -> None:
        bars = self._broker.reqHistoricalData(
            a.id.contract,
            endDateTime="",
            durationStr=str(HISTORICAL_YEARS) + " Y",
            barSizeSetting="1 day",
            whatToShow="OPTION_IMPLIED_VOLATILITY",
            useRTH=True,
            formatDate=1,
        )
        return History(self._translator.translate_bars(a.id.code, bars))

    def get_optionchain(self, asset: Asset, expiration: datetime.date) -> List[Option]:
        chains = self._broker.reqSecDefOptParams(
            asset.id.contract.symbol,
            "",
            asset.id.contract.secType,
            asset.id.contract.conId,
        )

        chain = next(
            c
            for c in chains
            if c.tradingClass == asset.id.contract.symbol and c.exchange == "SMART"
        )

        self._log.debug(f"Total chain elements {len(chain)}")
        if chain:
            underlying_price = asset.current.market_price
            # width = (a.current.stdev * 2) * underlying_price
            width = underlying_price * 0.1
            min_strike_price = underlying_price - width
            max_strike_price = underlying_price + width
            strikes = sorted(
                strike
                for strike in chain.strikes
                if min_strike_price < strike < max_strike_price
            )
            rights = ["P", "C"]

            # Create the options contracts
            contracts = [
                IBOption(
                    asset.id.contract.symbol,
                    format_ib_date(expiration),
                    strike,
                    right,
                    "SMART",
                )
                for right in rights
                # for expiration in expirations
                for strike in strikes
            ]
            q_contracts = []
            # IB has a limit of 50 requests per second
            for c in chunks(contracts, 50):
                q_contracts += self._broker.qualifyContracts(*c)
                self._broker.sleep(1)

            tickers = []
            # print("Contracts: {} Unqualified: {}".
            #      format(len(contracts), len(contracts) - len(q_contracts)))

            for q in chunks(q_contracts, 50):
                tickers += self._broker.reqTickers(*q)
                self._broker.sleep(1)

            return self.create_options(asset, q_contracts)

    def create_options(
            self, asset: Asset, q_contracts: List[Contract]
    ) -> Dict[str, Option]:
        tickers = []
        for q in chunks(q_contracts, 50):
            tickers += self._broker.reqTickers(*q)
            self._broker.sleep(1)
        # options = []
        options = {}
        for t in tickers:
            expiration = parse_ib_date(t.contract.lastTradeDateOrContractMonth)
            strike = float(t.contract.strike)
            right = RightType.Call if t.contract.right == "C" else RightType.Put
            delta = gamma = theta = vega = None
            option_price = (
                implied_volatility
            ) = underlying_price = underlying_dividends = None

            if t.modelGreeks:
                delta = t.modelGreeks.delta
                gamma = t.modelGreeks.gamma
                theta = t.modelGreeks.theta
                vega = t.modelGreeks.vega
                option_price = t.modelGreeks.optPrice
                implied_volatility = t.modelGreeks.impliedVol
                underlying_price = t.modelGreeks.undPrice
                underlying_dividends = t.modelGreeks.pvDividend
            opt_id = OptionId(
                underlying_id=asset.id,
                asset_type=AssetType.Option,
                expiration=expiration,
                strike=strike,
                right=right,
                multiplier=t.contract.multiplier,
                contract=t.contract,
            )
            opt = Option(
                id=opt_id,
                high=t.high,
                low=t.low,
                close=t.close,
                bid=t.bid if not t.bid == -1 else None,
                bid_size=t.bidSize,
                ask=t.ask if not t.ask == -1 else None,
                ask_size=t.askSize,
                last=t.last,
                last_size=t.lastSize,
                option_price=option_price,
                volume=t.volume,
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                iv=implied_volatility,
                underlying_price=underlying_price,
                underlying_dividends=underlying_dividends,
                time=t.time,
            )

            # options.append(opt)
            options[f"{strike}{right.value}"] = opt
        return options


def chunks(l: list, n: int) -> list:
    # For item i in a range that is a lenght of l
    for i in range(0, len(l), n):
        # Create an index range for l of n items:
        yield l[i: i + n]
