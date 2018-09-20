#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug  5 07:21:38 2018

@author: ilia
"""
import datetime
import logging
from typing import List, Dict
from pathlib import Path

from ib_insync.ib import IB, Contract
from ib_insync.contract import Index, Option, Stock
from ib_insync.objects import (AccountValue, Position, Fill,
                               CommissionReport, ComboLeg)
from ib_insync.order import Trade, LimitOrder, StopOrder
from optopus.data_objects import (AssetType,
                                  Asset, AssetData, OptionData,
                                  RightType,
                                  OptionMoneyness, BarData,
                                  PositionData, OwnershipType,
                                  Account,
                                  OrderStatus,
                                  TradeData, StrategyType, Strategy)
from optopus.data_manager import DataAdapter
from optopus.settings import (CURRENCY, HISTORICAL_YEARS, DTE_MAX, DTE_MIN,
                              EXPIRATIONS)
from optopus.utils import nan, parse_ib_date, format_ib_date


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

    def disconnect(self) ->None:
        self._broker.disconnect()

    def sleep(self, time: float) -> None:
        self._broker.sleep(time)
        
    def _onOrderStatusEvent(self, trade: Trade):
        self.emit_order_status(self._translator.translate_trade(trade))

    def place_orders(self, strategy: Strategy) -> None:
        """Place a orders at the market. 
        
        https://interactivebrokers.github.io/tws-api/bracket_order.html
        """

        #ownership = 'BUY' if parent_order.ownership == OwnershipType.Buyer else 'SELL'
        #reverse_ownership = 'BUY' if ownership == 'SELL' else 'SELL'
        contract = Contract()
        contract.symbol = strategy.code
        contract.secType = 'BAG'
        contract.exchange = 'SMART'
        contract.currency = strategy.currency.value
        contract.comboLegs = []
        
        #order = Order()
        #order.orderType = 'LMT'
        #order.totalQuantity = 1
        #order.orderComboLegs = []
        
        # ComboLegs (everythin but the price)
        
        
        for leg in strategy.legs.values():
            leg_order = ComboLeg()
            leg_order.conId = leg.option.contract.conId
            leg_order.ratio = leg.ratio
            leg_order.action = leg.ownership.value
            contract.comboLegs.append(leg_order)
            
            
        
        order = LimitOrder(action=strategy.ownership.value,
                           totalQuantity=strategy.quantity,
                           lmtPrice=strategy.spread_entry_price,
                           orderRef=strategy.strategy_id + '_PO',
                           orderId=self._broker.client.getReqId(),
                           tif='GTC',
                           transmit=True)
        self._broker.placeOrder(contract, order)

"""

        take_profit = LimitOrder(action=reverse_ownership,
                                 totalQuantity=take_profit_order.quantity,
                                 lmtPrice=take_profit_order.price,
                                 orderRef=take_profit_order.order_id,
                                 orderId=self._broker.client.getReqId(),
                                 tif='GTC',
                                 transmit=False,
                                 parentId=parent.orderId)
        self._broker.placeOrder(contract, take_profit)

        stop_loss = StopOrder(action=reverse_ownership,
                              totalQuantity=stop_loss_order.quantity,
                              stopPrice=stop_loss_order.price,
                              orderRef=stop_loss_order.order_id,
                              orderId=self._broker.client.getReqId(),
                              tif='GTC',
                              transmit=True,
                              parentId=parent.orderId)
        self._broker.placeOrder(contract, stop_loss)
"""
    


class IBTranslator:
    """Translate the IB tags and values to Ocptopus"""
    def __init__(self) -> None:
        self._sectype_translation = {'STK': AssetType.Stock,
                                     'OPT': AssetType.Option,
                                     'FUT': AssetType.Future,
                                     'CASH': AssetType.Future,
                                     'IND': AssetType.Index,
                                     'CFD': AssetType.CFD,
                                     'BOND': AssetType.Bond,
                                     'CMDTY': AssetType.Commodity,
                                     'FOP': AssetType.FuturesOption,
                                     'FUND': AssetType.MutualFund,
                                     'IOPT': AssetType.Warrant}

        self._right_translation = {'C': RightType.Call,
                                   'P': RightType.Put}

        self._order_status_translation = {'ApiPending': OrderStatus.APIPending,
                                          'PendingSubmit': OrderStatus.PendingSubmit,
                                          'PendingCancel': OrderStatus.PendingCancel,
                                          'PreSubmitted': OrderStatus.PreSubmitted,
                                          'Submitted': OrderStatus.Submitted,
                                          'ApiCancelled': OrderStatus.APICancelled,
                                          'Cancelled': OrderStatus.Cancelled,
                                          'Filled': OrderStatus.Filled,
                                          'Inactive': OrderStatus.Inactive}

        self._ownership_translation = {'BUY': OwnershipType.Buyer,
                                       'SELL': OwnershipType.Seller}
        
        self._strategy_translation = {'SP': StrategyType.ShortPut,
                                      'SPVS': StrategyType.ShortPutVerticalSpread,
                                      'SCVS': StrategyType.ShortCallVerticalSpread}

    def translate_account(self, values: List[AccountValue]) -> Account:
        account = Account()
        for v in values:
            if v.currency == CURRENCY.value:
                if v.tag == 'AvailableFunds':
                    account.funds = v.value
                elif v.tag == 'BuyingPower':
                    account.buying_power = v.value
                elif v.tag == 'TotalCashValue':
                    account.cash = v.value
                elif v.tag == 'DayTradesRemaining':
                    account.max_day_trades = v.value
                elif v.tag == 'NetLiquidation':
                    account.net_liquidation = v.value
                elif v.tag == 'InitMarginReq':
                    account.initial_margin = v.value
                elif v.tag == 'MaintMarginReq':
                    account.maintenance_margin = v.value
                elif v.tag == 'ExcessLiquidity':
                    account.excess_liquidity = v.value
                elif v.tag == 'Cushion':
                    account.cushion = v.value
                elif v.tag == 'GrossPositionValue':
                    account.gross_position_value = v.value
                elif v.tag == 'EquityWithLoanValue':
                    account.equity_with_loan = v.value
                elif v.tag == 'SMA':
                    account.SMA = v.value
        return account

    def translate_position(self, item: Position) -> PositionData:
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

        position = PositionData(code=code,
                                asset_type=asset_type,
                                expiration=expiration,
                                ownership=ownership,
                                quantity=abs(item.position),
                                strike=item.contract.strike,
                                right=right,
                                average_cost=item.avgCost)
        return position

    def translate_trade(self, item: Trade) -> TradeData:

        #print(item)
        
        order_id = item.order.orderRef
        status = self._order_status_translation[item.orderStatus.status]
        remaining = item.orderStatus.remaining
        try:
            commission = item.commissionReport.commission
        except AttributeError as e:
            commission = None

        trade = TradeData(order_id=order_id,
                          status=status,
                          remaining=remaining,
                          commission=commission)
        return trade

    def translate_bars(self, code: str, ibbars: list) -> list:
        bars = []
        for ibb in ibbars:
            b = BarData(code=code,
                        bar_time=ibb.date,
                        bar_open=ibb.open,
                        bar_high=ibb.high,
                        bar_low=ibb.low,
                        bar_close=ibb.close,
                        bar_average=ibb.average,
                        bar_volume=ibb.volume,
                        bar_count=ibb.barCount)
            bars.append(b)
        return bars


class IBDataAdapter(DataAdapter):
    def __init__(self, broker: IB, translator: IBTranslator) -> None:
        self._broker = broker
        self._translator = translator
        self._log = logging.getLogger(__name__)

    def get_account_values(self):
        values = self._broker.accountValues()
        account = self._translator.translate_account(values)
        return account

    def get_positions(self) -> Dict[str, PositionData]:
        positions = self._broker.positions()
        positions_data = {}
        for p in positions:
            pd = self._translator.translate_position(p)
            positions_data[pd.position_id] = pd
        return positions_data

    def initialize_assets(self, assets: List[Asset]) -> dict:
        contracts = []
        for asset in assets:
            if asset.asset_type == AssetType.Index:
                contracts.append(Index(asset.code,
                                       currency=CURRENCY.value))
            elif asset.asset_type == AssetType.Stock:
                contracts.append(Stock(asset.code,
                                       exchange='SMART',
                                       currency=CURRENCY.value))
        # It works if len(contracts) < 50. IB limit.
        q_contracts = self._broker.qualifyContracts(*contracts)
        if len(q_contracts) == len(assets):
            return {c.symbol: c for c in q_contracts}
        else:
            raise ValueError('Error: ambiguous contracts')

    def get_assets(self, assets: List[Asset]) -> List[AssetData]:
        contracts = [a.contract for a in assets]
        tickers = self._broker.reqTickers(*contracts)
        data = []
        for t in tickers:
            asset_type = self._translator._sectype_translation[t.contract.secType]
            ad = AssetData(code=t.contract.symbol,
                           asset_type=asset_type,
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
                           contract=t.contract)
            data.append(ad)
        return data

    def get_historical(self, a: Asset) -> None:
        bars = self._broker.reqHistoricalData(a.contract,
                                              endDateTime='',
                                              durationStr=str(HISTORICAL_YEARS) + ' Y',
                                              barSizeSetting='1 day',
                                              whatToShow='TRADES',
                                              useRTH=True,
                                              formatDate=1)
        return self._translator.translate_bars(a.code, bars)

    def get_historical_IV(self, a: Asset) -> None:
        bars = self._broker.reqHistoricalData(a.contract,
                                              endDateTime='',
                                              durationStr=str(HISTORICAL_YEARS) + ' Y',
                                              barSizeSetting='1 day',
                                              whatToShow='OPTION_IMPLIED_VOLATILITY',
                                              useRTH=True,
                                              formatDate=1)
        return self._translator.translate_bars(a.code, bars)


    def get_optionchain(self, a: Asset, expiration: datetime.date) -> List[OptionData]:
        chains = self._broker.reqSecDefOptParams(a.contract.symbol,
                                                 '',
                                                 a.contract.secType,
                                                 a.contract.conId)

        chain = next(c for c in chains
                     if c.tradingClass == a.contract.symbol
                     and c.exchange == 'SMART')
        
        self._log.debug(f'Total chain elements {len(chain)}')
        if chain:
            underlying_price = a.current.market_price
            #width = (a.current.stdev * 2) * underlying_price
            width = underlying_price * 0.01
            #expirations = [exp for exp in chain.expirations]
            #expirations = [e for e in expirations if parse_ib_date(e) in EXPIRATIONS]
            #expirations = [e for e in expirations if (parse_ib_date(e) - datetime.datetime.now().date()).days < DTE_MAX and 
            #                                        (parse_ib_date(e) - datetime.datetime.now().date()).days > DTE_MIN]
            #expirations = sorted(expirations)
            min_strike_price = underlying_price - width
            max_strike_price = underlying_price + width
            strikes = sorted(strike for strike in chain.strikes
                       if min_strike_price < strike < max_strike_price)
            rights = ['P', 'C']

            # Create the options contracts
            contracts = [Option(a.contract.symbol,
                                format_ib_date(expiration),
                                strike,
                                right,
                                'SMART')
                                for right in rights
                                #for expiration in expirations
                                for strike in strikes]
            q_contracts = []
            # IB has a limit of 50 requests per second
            for c in chunks(contracts, 50):
                q_contracts += self._broker.qualifyContracts(*c)
                self._broker.sleep(1)

            tickers = []
            #print("Contracts: {} Unqualified: {}".
            #      format(len(contracts), len(contracts) - len(q_contracts)))
            
            for q in chunks(q_contracts, 50):
                tickers += self._broker.reqTickers(*q)
                self._broker.sleep(1)

            return self.get_options(q_contracts)

    def get_options(self, q_contracts: List[Contract]) -> List[OptionData]:
            tickers = []
            for q in chunks(q_contracts, 50):
                tickers += self._broker.reqTickers(*q)
                self._broker.sleep(1)
            options = []

            for t in tickers:
                # There others Greeks for bid, ask and last prices
                delta = gamma = theta = vega = option_price = \
                implied_volatility = underlying_price = \
                underlying_dividends = nan

                if t.modelGreeks:
                    delta = t.modelGreeks.delta
                    gamma = t.modelGreeks.gamma
                    theta = t.modelGreeks.theta
                    vega = t.modelGreeks.vega
                    option_price = t.modelGreeks.optPrice
                    implied_volatility = t.modelGreeks.impliedVol
                    underlying_price = t.modelGreeks.undPrice
                    underlying_dividends = t.modelGreeks.pvDividend

                opt = OptionData(
                        code=t.contract.symbol,
                        expiration=parse_ib_date(t.contract.lastTradeDateOrContractMonth),
                        strike=float(t.contract.strike),
                        right=RightType.Call if t.contract.right =='C' else RightType.Put,
                        high=t.high,
                        low=t.low,
                        close=t.close,
                        bid=t.bid,
                        bid_size=t.bidSize,
                        ask=t.ask,
                        ask_size=t.askSize,
                        last=t.last,
                        last_size=t.lastSize,
                        option_price=option_price,
                        currency=CURRENCY,
                        volume=t.volume,
                        delta=delta,
                        gamma=gamma,
                        theta=theta,
                        vega=vega,
                        implied_volatility=implied_volatility,
                        underlying_price=underlying_price,
                        underlying_dividends=underlying_dividends,
                        time=t.time,
                        contract=t.contract)

                options.append(opt)
            return options


def is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception as e:
        return False


def chunks(l: list, n: int) -> list:
    # For item i in a range that is a lenght of l
    for i in range(0, len(l), n):
        # Create an index range for l of n items:
        yield l[i:i+n]
