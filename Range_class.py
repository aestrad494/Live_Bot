from ib_insync import *
import pandas as pd
import numpy as np
import datetime
import calendar
import time
from IPython.display import clear_output
import threading
from nested_lookup import nested_lookup
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import pytz
import smtplib
import math

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
        
    '''def connection(self):
        global ib
        ib = IB()
        return(ib.connect('127.0.0.1', 7497, clientId = self.client))'''
    
    def create_contract(self):
        if (self.type_c == 'forex'):
            contract = Forex(self.inst)
        elif (self.type_c == 'stock'):
            contract = Stock(self.inst, 'SMART', 'USD')
        elif (self.type_c == 'future'):
            contract = Future(self.inst, '20190621', 'GLOBEX')
        return (contract)    
    
    def req_mkt_data(self, ib, contract):
        return(ib.reqMktData(contract, '', False, False))
    
    def req_real_time_bars(self, contract):
    	if (self.type_c == 'forex'):
    		pr = 'MIDPOINT'
    	elif (self.type_c == 'stock') or (self.type_c == 'future'):
    		pr = 'TRADES'
    	return(ib.reqRealTimeBars(contract, 5, pr, useRTH = True))

    def executions(self, ib):
        executions = ib.executions()
        return(util.tree(executions))
    
    def fills(self, ib):
        fills = ib.fills()
        return(util.tree(fills))
    
    def day_and_hour(self):
        now = datetime.datetime.now()
        today = now.strftime("%Y/%m/%d" )
        hour = now.strftime("%H:%M:%S")
        my_date = now.today()
        weekday = calendar.day_name[my_date.weekday()] 
        return([today, hour, weekday])
    
    def ask_bid(self, ib, contract):
        tick = ib.ticker(contract)
        bid = tick.bid
        ask = tick.ask
        return ([ask, bid])
    
    def allow_trading_by_day(self, weekday):   
        if (weekday == 'Saturday') or (weekday == 'Sunday'):
            allow_trading = False
        else:
            allow_trading = True
        return(allow_trading) 
    
    def allow_trading_by_hour(self, current, weekday):
        [h,m,s] = self.fin_hour.split(":")
        h = int(h)
        if (weekday == 'Friday') and (h > 16):
            self.fin_hour = '16:00:00'
        if (current > self.ini_hour) and (current < self.fin_hour):     
            operable = True
        else:
            operable = False
        return (operable)
    
    def download_data(self, ib, contract):
        if (self.tam>1):
        	temp = str(self.tam) + ' mins'
        else:
        	temp = str(self.tam) + ' min'

        pr = ''
        if (self.type_c == 'forex'):
        	pr = 'MIDPOINT'
        elif (self.type_c == 'stock') or (self.type_c == 'future'):
        	pr = 'TRADES'
    	
        hist = []
        hist = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='2 D',
                barSizeSetting=temp,
                whatToShow=pr,
                useRTH=True,
                keepUpToDate=True)#,
                #formatDate=1)
        '''hist = util.df(hist)
        hist = hist.reset_index()
        hist = hist.set_index('date')
        hist = hist[['open', 'high', 'low', 'close']]'''
        return(hist)
    
    def convert_datetime_timezone(self, dt):
        dt = dt[:-6]
        tz1 = pytz.timezone("UTC")
        tz2 = pytz.timezone("America/Bogota")

        dt = datetime.datetime.strptime(dt,"%Y-%m-%d %H:%M:%S")
        dt = tz1.localize(dt)
        dt = dt.astimezone(tz2)
        dt = dt.strftime("%Y-%m-%d %H:%M:%S")
        dt = datetime.datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')

        return(dt)
    
    def convert_table(self, table):
        try:
            global table_df
            table_df = util.df(table)
            table_df['time'] = table_df['time'].astype(str)
            table_df['time'] = table_df.time.apply(self.convert_datetime_timezone)
            table_df = table_df.set_index('time')
            table_df = table_df[['open_', 'high', 'low', 'close']]

            global resampled_df

            t = str(self.tam) + 'Min'
            Open = table_df.open_.resample(t).first()
            High = table_df.high.resample(t).max()
            Low = table_df.low.resample(t).min()
            Close = table_df.close.resample(t).last()
            resampled_df = pd.concat([Open, High, Low, Close], axis = 1)
            resampled_df.columns = ['open', 'high', 'low', 'close']
            return(resampled_df)
        except:
            return(False)
    
    def concatenate_df(self, hist, resampled_df, flag):
        try:
            if (flag == False):
                index_row = hist.index[-1] + datetime.timedelta(minutes=self.tam) 
                hist = pd.concat([hist,resampled_df.loc[index_row:]], ignore_index=False, sort=False).fillna(0)

            if (flag == True):
                hist = pd.concat([hist,resampled_df.iloc[-1:]], ignore_index=False, sort=False).fillna(0)
                if (hist.index[-1] == hist.index[-2]):
                    open_l = hist.open.iloc[-2]
                    high_l = max(hist.high.iloc[-1], hist.high.iloc[-2])
                    low_l = min(hist.low.iloc[-1], hist.low.iloc[-2])
                    close_l = hist.close.iloc[-1]
                    last_row = [open_l, high_l, low_l, close_l, 0, 0]
                    hist = hist.iloc[:-1]
                    hist.iloc[-1] = last_row  
            return(hist)
        except:
            return(False)
        
    def max_and_min(self, df, today, hour_int, digits):
        df['max'] = df.high.rolling(self.num_bars).max()
        df['min'] = df.low.rolling(self.num_bars).min()

        index = today + " " + hour_int

        maximum = round(df['max'].loc[index],digits)
        minimum = round(df['min'].loc[index],digits)
        return ([maximum,minimum])
    
    def lots(self, account, risk, maximum, minimum):
        lots = math.floor((account*risk)/(maximum-minimum))
        return(lots)
    
    def order_send(self, ib, order_type, lots, contract):
        order_entry = MarketOrder(order_type, lots)
        trade_entry = ib.placeOrder(contract, order_entry)
        margin_entry = float(ib.whatIfOrder(contract, order_entry).initMarginChange)
        entry_id = order_entry.orderId
        return ([entry_id,margin_entry])
    
    def bracket_stop_order_send(self, ib, order_type, lots, contract, entry_price, target, stop):
        order_bracket = ib.bracketStopOrder(order_type, lots, entry_price, target, stop)
        orders_id = []
        orders_total = []
        for order in order_bracket:
            ib.placeOrder(contract, order)
            orders_id.append(order.orderId)
            orders_total.append(order)
        return([orders_id,orders_total])
    
    def order_values(self,execution_list, order_id, lots, exit = False):
    	indexes = []
    	commission = []
    	lot = []
    	prices = []
    	profit = []

    	for i in range(len(execution_list)):
    		if ('orderId' and 'clientId') in execution_list[i][1]['Execution']:
    			if ((nested_lookup('orderId',execution_list[i])[0] == order_id) and (nested_lookup('clientId',execution_list[i])[0] == self.client)):
    				indexes.append(i)

    	for j in indexes:
    		commission.append(nested_lookup('commission',execution_list[j])[0])
    		lot.append(round(nested_lookup('shares',execution_list[j])[0],2))
    		prices.append(round(nested_lookup('price',execution_list[j])[0],5))
    		if exit == True:
    			try:
    				profit.append(nested_lookup('realizedPNL',execution_list[j])[0])
    			except:
    				profit = [0]

    	price = sum((np.array(prices) * np.array(lot))/lots)

    	if exit == True:
    		return([sum(commission),price, sum(profit)])
    	else:
    		return([sum(commission),price])
    
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
            server.login("ibpy.notifications@gmail.com", "carpe2019")
            message = 'Subject: {}\n\n{}'.format(subject, msg)
            server.sendmail(mails, mails, message)
            server.quit()
            return(True)
        except:
            return(False)