#!/usr/bin/env python
# coding: utf-8

# Importing Libraries
from ib_insync import *
#util.startLoop()
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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
util.patchAsyncio()
from Range_class import Ranguito

#  Instance Variables
inst =  input('\tInstrument: ') #'ES'               'EURUSD'  
type_con = 'stock'#input('\tContract type: ') #'future'        'forex'
num_bars = 1 #int(input('\tNumber of bars: ')) #1              1
tempo = 1 #int(input('\tTemporality: ')) #5                 1
target = float(input('\tTarget: ')) #0.80             0.00015
hora_ini = "09:30:00"   #input('\tInitial Hour: ') #'15:40:00'     
hora_fin = "15:30:00"    #input('\tFinal Hour: ') #'18:48:00'     
client = int(input('\tClient ID: ')) #3 

tick_val = 0
#Code variables
if type_con == 'forex':
    tick_val = 0.00001
    digits = 5
if (type_con == 'stock') or (type_con == 'future'):
    tick_val = 0.01
    digits = 2

account = 20000
risk = 0.001
mail_1 = "aestrad494@gmail.com"
mail_2 = "ibpy.notifications@gmail.com"
mails = [mail_2]#, mail_2]
obj_ticks = float(target)/tick_val

maxi = 0                  #maximum price of the range
mini = 0                  #minimum price of the price
lots = 0                  #Lots quantity
buys = 0                  #number of total opened buys
sells = 0                 #number of total opened sells
entry_price_b = 0         #entry price of buy operations
entry_price_s = 0         #entry price of sell operations
profit_buy = 0            #current profit of buy operations
profit_sell = 0           #current profit of sell operations
exit_price_b = 0          #exit price of buy operations
exit_price_s = 0          #exit price of sell operations
commission_entry_buy = 0  #commission of entry buy
commission_entry_sell = 0 #commission of entry sell
commission_exit_buy = 0   #commission of exit buy
commission_exit_sell = 0  #commission of exit sell
id_buy_exit = 0
id_sell_exit = 0
weekday = ''
margin_buy = 0
margin_sell = 0

range_calcu = False     #flag that indicates if range has been calculated
mail_buy_entry = True   #flag that indicates if an email for buy entry has been sent
mail_sell_entry = True  #flag that indicates if an email for sell entry has been sent
mail_buy_exit = True    #flag that indicates if an email for buy exit has been sent
mail_sell_exit = True   #flag that indicates if an email for sell exit has been sent
hist_update = False
b_sells = False
b_buys = False
cancel_orders = False
valid_day = False
valid_hour = False

#Instantiating Ranguito and IB
ranguito = Ranguito(inst,type_con,num_bars,tempo,target,hora_ini,hora_fin,client)
ib = IB()

# Connection to IB
print(ib.connect(host='127.0.0.1',port=7497,clientId=client))

#Contract Creation
#contract = Stock(inst, 'SMART', 'USD')
contract = Forex('EURUSD')

# Function that returns current date, hour and week day
def times():
    try:
        global today, hour, weekday
        today, hour, weekday = ranguito.day_and_hour()
    except:
        pass
    
# Function that allows or not doing trading
def allowing_trading():
    try:
        global valid_day, valid_hour
        valid_day = ranguito.allow_trading_by_day(weekday)
        valid_hour = ranguito.allow_trading_by_hour(hour, weekday)
    except:
        pass

# Downloading Historical Data
histo = ranguito.download_data(ib,contract)
hist = util.df(histo)
hist = hist.reset_index()
hist = hist.set_index('date')
hist = hist[['open', 'high', 'low', 'close']]

# Function that transforms Historical Data in DataFrame
def convert_historical():
    global hist
    global hist_update
    hist = util.df(histo)
    hist = hist.reset_index()
    hist = hist.set_index('date')
    hist = hist[['open', 'high', 'low', 'close']]
    hist_update = True
    return(hist)

# Getting hour to calculate the range
[h_i, m_i, s_i] = hora_ini.split(":")
h_i = int(h_i)
m_i = int(m_i)

hour_exe = str(datetime.timedelta(hours=h_i, minutes=m_i) + datetime.timedelta(minutes=num_bars*tempo))
hour_range = str(datetime.timedelta(hours=h_i, minutes=m_i) + datetime.timedelta(minutes=num_bars*tempo - tempo))

# Function that calculates the maximum and minimum of the range
def calc_range():
    global maxi, mini 
    global range_calcu
    
    try:
        if (valid_day == True) and (valid_hour == True):
            hour_d = datetime.datetime.strptime(hour, '%H:%M:%S')
            hour_exe_d = datetime.datetime.strptime(hour_exe, '%H:%M:%S')
            if (hour_d > hour_exe_d) and (range_calcu == False):
                maxi,mini = ranguito.max_and_min(hist, today, hour_range, digits)
                range_calcu = True
                print('Range calculated')
    except:
        pass

# Function that calculates lots 
def entry_lots():
    global lots
    if (range_calcu == True):
        lots = ranguito.lots(account, risk, maxi, mini)
        print('lots quantity calculated')

lots = 20000

# Function that places stop bracket orders
async def place_orders():
    global b_buys, b_sells
    global id_buy, id_sell
    global id_buy_entry, id_sell_entry
    global margin_entry_buy, margin_entry_sell
    
    if (maxi > 0 or mini > 0) and lots > 0:
        #BUY-----------------
        if not b_buys:
            id_buy, orders_buy = ranguito.bracket_stop_order_send(ib, 'BUY', lots, contract, maxi, maxi + target, mini)
            margin_entry_buy = float(ib.whatIfOrder(contract, orders_buy[0]).initMarginChange)
            id_buy_entry = id_buy[0]
            b_buys = True
            print('Bracket stop buy order sent')

        #SELL--------------
        if not b_sells:
            id_sell, orders_sell = ranguito.bracket_stop_order_send(ib, 'SELL', lots, contract, mini, mini - target, maxi)
            margin_entry_sell = float(ib.whatIfOrder(contract, orders_sell[0]).initMarginChange)
            id_sell_entry = id_sell[0]
            b_sells = True
            print('Bracket stop sell order sent')

# Function that gets entry price and commission
def calc_entry_values():
    global fills
    global entry_price_b, entry_price_s
    global commission_entry_buy, commission_entry_sell
    
    fills = ranguito.fills(ib)
    try:
        commission_entry_buy, entry_price_b = ranguito.order_values(fills, id_buy_entry, lots)
        commission_entry_sell, entry_price_s = ranguito.order_values(fills, id_sell_entry, lots)
    except:
        pass

# Function that calculates the required margin
def calc_margin():
    global margin_buy, margin_sell
    
    if entry_price_b > 0:
        margin_buy = round(ranguito.required_margin('BUY', entry_price_b, lots),2)
    if entry_price_s > 0:
        margin_sell = round(ranguito.required_margin('SELL', entry_price_s, lots),2)

# Function that gets exit price and commission
def calc_exit_values():
    global exit_price_b, exit_price_s
    global commission_exit_buy, commission_exit_sell
    global profit_s, profit_b
    global id_sell_exit, id_buy_exit
    
    if b_buys or b_sells:  
        if id_buy[1] in nested_lookup('orderId',fills):
            id_sell_exit = id_buy[1]
        elif id_buy[2] in nested_lookup('orderId',fills):
            id_sell_exit = id_buy[2]
        if id_sell[1] in nested_lookup('orderId',fills):
            id_buy_exit = id_sell[1]
        elif id_sell[2] in nested_lookup('orderId',fills):
            id_buy_exit = id_sell[2]
        
        #exit from sells
        commission_exit_buy, exit_price_b, profit_s = ranguito.order_values(fills, id_buy_exit, lots, exit = True)
        #exit from buys
        commission_exit_sell, exit_price_s, profit_b = ranguito.order_values(fills, id_sell_exit, lots, exit = True)

# Function that calculates the final profit in usd and ticks
def calc_final_profit():
    global final_profit_buy, final_profit_sell
    global final_profit_buy_usd, final_profit_sell_usd
    if (entry_price_b > 0) and (exit_price_s > 0):
        final_profit_buy = round((exit_price_s - entry_price_b)/tick_val,0)
        final_profit_buy_usd = round(((exit_price_s - entry_price_b) * lots) - commission_entry_buy - commission_exit_sell,2)
    if (entry_price_s > 0) and (exit_price_b > 0):
        final_profit_sell = round((entry_price_s - exit_price_b)/tick_val,0)
        final_profit_sell_usd = round(((entry_price_s - exit_price_b) * lots) - commission_entry_sell - commission_exit_buy,2)

# Function that closes every open order
async def close_all():
    global exit_price_b, exit_price_s
    global commission_exit_buy, commission_exit_sell
    global profit_s, profit_b
    global id_sell_exit, id_buy_exit
    global cancel_orders
    if (not valid_day or not valid_hour) and (b_buys or b_sells) and (not cancel_orders):
        ib.reqGlobalCancel()
        cancel_orders = True
        if exit_price_b == 0 or exit_price_s == 0:
            if ib.positions()[0].contract.symbol == inst:
                open_lots = ib.positions()[0].position
                if open_lots > 0:
                    id_sell_exit, margin_sell_exit = ranguito.order_send(ib, 'SELL', abs(open_lots), contract)
                    commission_exit_sell, exit_price_s, profit_b = ranguito.order_values(fills, id_sell_exit, lots, exit = True)
                else:
                    id_buy_exit, margin_buy_exit = ranguito.order_send(ib, 'BUY', abs(open_lots), contract)
                    commission_exit_buy, exit_price_b, profit_s = ranguito.order_values(fills, id_buy_exit, lots, exit = True)

# Function that sends emails with entry and exit information
def sending_emails():
    global mail_buy_entry, mail_sell_entry, mail_buy_exit, mail_sell_exit
    #Mail for entries
    if (entry_price_b > 0) and (mail_buy_entry == True):
        subject_entry_buy = 'Entry Buy Notification: Ranguito'
        msg_entry_buy = 'Buy Market in ' + str(inst) + '\nPrice: ' + str(entry_price_b) + \
                        '\nLots: ' + str(lots) + '\nAt: ' + str(hour) + \
                        '\nReq.Margin: ' + str(margin_buy) + \
                        '\nReq.Margin(ib): ' + str(margin_entry_buy)
        ranguito.send_email(subject_entry_buy, msg_entry_buy, mails)
        mail_buy_entry = False
    if (entry_price_s > 0) and (mail_sell_entry == True):  
        subject_entry_sell = 'Entry Sell Notification: Ranguito'
        msg_entry_sell = 'Sell Market in ' + str(inst) + '\nPrice: ' + str(entry_price_s) + \
                        '\nLots: ' + str(lots) + '\nAt: ' + str(hour) +  \
                        '\nReq.Margin: ' + str(margin_sell) + \
                        '\nReq.Margin(ib): ' + str(margin_entry_sell)
        ranguito.send_email(subject_entry_sell, msg_entry_sell, mails)
        mail_sell_entry = False
    
    #Mail for exits
    if (mail_buy_entry == False) and (exit_price_s > 0) and (mail_buy_exit == True) :
        subject_exit_buy = 'Exit Buy Notification: Ranguito'
        msg_exit_buy = 'Buy Closed in ' + str(inst) + '\nPrice: ' + str(exit_price_s) +  \
                        '\nProfit(ticks): ' + str(final_profit_buy) + \
                        '\nProfit(USD): ' + str(final_profit_buy_usd) +  \
                        '\nProfit(USD-ib): ' + str(profit_b) + \
                        '\ncommissions: ' + str(commission_entry_buy + commission_exit_sell) + \
                        '\nAt: ' + str(hour)
        ranguito.send_email(subject_exit_buy, msg_exit_buy, mails)
        mail_buy_exit = False
    if (mail_sell_entry == False) and (exit_price_b > 0) and (mail_sell_exit == True) :
        subject_exit_sell = 'Exit Sell Notification: Ranguito'
        msg_exit_sell = 'Sell Closed in ' + str(inst) + '\nPrice: ' + str(exit_price_b) + \
                        '\nProfit(ticks): ' + str(final_profit_sell) + \
                        '\nProfit(USD): ' + str(final_profit_sell_usd) +  \
                        '\nProfit(USD-ib): ' + str(profit_s) + \
                        '\ncommissions: ' + str(commission_entry_sell + commission_exit_buy) + \
                        '\nAt: ' + str(hour)
        ranguito.send_email(subject_exit_sell, msg_exit_sell, mails)
        mail_sell_exit = False


# Background Execution
if __name__ == '__main__':

    # Instantiating Schedulers
    sched = BackgroundScheduler()
    sched.start()

    sched_async = AsyncIOScheduler()
    sched_async.start()

    sched.add_job(times,'interval', seconds=1)
    sched.add_job(allowing_trading,'interval', seconds=1)
    sched.add_job(convert_historical,trigger = 'cron', minute = '0-59/1', second = '01')
    sched.add_job(calc_range,trigger = 'cron', hour = '8-22', minute = '0-59', second = '0-59/1')
    #sched.add_job(entry_lots,trigger = 'cron', hour = '8-20', minute = '0-59', second = '0-59/1')
    sched_async.add_job(place_orders,trigger = 'interval', seconds = 1)
    #sched_async.add_job(place_orders,trigger = 'cron', minute = '0-59', second = '0-59/1')
    sched.add_job(calc_entry_values,trigger = 'cron', hour = '8-22', minute = '0-59', second = '0-59/1')
    sched.add_job(calc_margin,trigger = 'cron', hour = '8-22', minute = '0-59', second = '0-59/1')
    sched.add_job(calc_exit_values,trigger = 'cron', hour = '8-22', minute = '0-59', second = '0-59/1')
    sched.add_job(calc_final_profit,trigger = 'cron', hour = '8-22', minute = '0-59', second = '0-59/1')
    sched_async.add_job(close_all,trigger = 'interval', seconds = 1)
    sched.add_job(sending_emails, trigger = 'cron', hour = '8-22', minute = '0-59', second = '0-59/10')

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            #ib.sleep(1)
            #util.sleep(1)
            asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        # Not strictly necessary if daemonic mode is enabled but should be done if possible
        scheduler.shutdown()