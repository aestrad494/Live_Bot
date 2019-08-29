from ib_insync import *
import pandas as pd
import numpy as np
from datetime import datetime
from nested_lookup import nested_lookup
import smtplib
from math import floor

ib = IB()

class Ranguito(IB):
    def __init__(self, inst, type_c, num_bars, tam, target, ini_hour, fin_hour, client):
        self.inst = inst
        self.type_c = type_c
        self.num_bars = num_bars
        self.tam = tam
        self.target = target
        self.ini_hour = ini_hour
        self.fin_hour = fin_hour
        self.client = client   
    
    def day_and_hour(self):
        today = datetime.now().strftime("%Y/%m/%d")
        hour = datetime.now().strftime("%H:%M:%S")
        weekday = datetime.now().today().weekday()
        return([today, hour, weekday])
    
    def allow_trading(self, current, weekday):
        if current > self.ini_hour and current < self.fin_hour and (weekday != 5 and weekday != 6):
            allow_trading = True
        else:
            allow_trading = False
        return(allow_trading)
    
    def download_data(self, ib, contract):
        if (self.tam>1):
            temp = str(self.tam) + ' mins'
        else:
            temp = str(self.tam) + ' min'

        if (self.type_c == 'forex'):
            pr = 'MIDPOINT'
        elif (self.type_c == 'stock') or (self.type_c == 'future'):
            pr = 'TRADES'

        hist = ib.reqHistoricalData(contract, endDateTime='', durationStr='2 D',
                barSizeSetting=temp, whatToShow=pr, useRTH=True, keepUpToDate=True)
        return(hist)
    
    def max_and_min(self, df, today, digits, account, risk):
        bars_range = df.loc[today+' '+self.ini_hour:,:].iloc[0:self.num_bars]
        maximum = round(bars_range['high'].max(),digits)
        minimum = round(bars_range['low'].min(),digits)
        lots = 20000#floor((account*risk)/(maximum-minimum))
        return ([maximum,minimum,lots])
    
    def order_send(self, ib, order_type, lots, contract):
        order_entry = MarketOrder(order_type, lots)
        trade_entry = ib.placeOrder(contract, order_entry)
        margin_entry = float(ib.whatIfOrder(contract, order_entry).initMarginChange)
        entry_id = order_entry.orderId
        return ([entry_id,margin_entry])
    
    def bracket_stop_order(self, ib, order_type, lots, contract, entry_price, target, stop):
        order_bracket = ib.bracketStopOrder(order_type, lots, entry_price, target, stop)
        orders_id = []
        orders_total = []
        for order in order_bracket:
            ib.placeOrder(contract, order)
            orders_id.append(order.orderId)
            orders_total.append(order)
        margin = float(ib.whatIfOrder(contract, orders_total[0]).initMarginChange)
        #return([orders_id,orders_total,margin])
        return([orders_id,order_bracket,margin])
    
    def order_values(self, execution_list, order_id, lots, exit = False):    
        indexes = []
        commission = []
        lot = []
        prices = []
        profit = []
        for trade in execution_list:
            if ('orderId' and 'clientId') in trade[1]['Execution']:
                if ((nested_lookup('orderId',trade)[0] == order_id) and (nested_lookup('clientId',trade)[0] == self.client)):
                    commission.append(nested_lookup('commission',trade)[0])
                    lot.append(round(nested_lookup('shares',trade)[0],2))
                    prices.append(round(nested_lookup('price',trade)[0],5))
                    if exit == True:
                        try:
                            profit.append(nested_lookup('realizedPNL',trade)[0])
                        except:
                            profit = [0]
        price = sum((np.array(prices) * np.array(lot))/lots)
        if exit == True:
            return([sum(commission),price, sum(profit)])
        else:
            return([sum(commission),price])
    
    def filled_id(self, execution_list, id_list):
        id_buy = 0
        id_sell = 0
        if id_list[0] in nested_lookup('orderId',execution_list):
            id_sell = id_list[0]
        elif id_list[1] in nested_lookup('orderId',execution_list):
            id_sell = id_list[1]
        if id_list[2] in nested_lookup('orderId',execution_list):
            id_buy = id_list[2]
        elif id_list[3] in nested_lookup('orderId',execution_list):
            id_buy = id_list[3]
        return([id_sell, id_buy])
    
    def required_margin(self, type_entry, price, lots):
        if type_entry == 'BUY':
            margin = price * lots * 0.25
        if type_entry == 'SELL':
            margin = price * lots * 0.30
        return(margin)

    def send_email(self, subject, msg, mails):
        try:
            server = smtplib.SMTP('smtp.gmail.com:587')
            server.ehlo()
            server.starttls()
            server.login("ibpy.notifications@gmail.com", "carpediem300*")
            message = 'Subject: {}\n\n{}'.format(subject, msg)
            server.sendmail(mails, mails, message)
            server.quit()
            return(True)
        except:
            return(False)