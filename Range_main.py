#!/usr/bin/env python
# coding: utf-8

# Range Bot
## Importing Libraries
from datetime import datetime, timedelta
from ib_insync import *
import pandas as pd
from math import floor
import threading
from time import sleep
from apscheduler.schedulers.background import BackgroundScheduler
from nested_lookup import nested_lookup
from Range_class import Ranguito
util.patchAsyncio()

## Input variables
initial_hour = '16:49:00'
final_hour = '16:52:00'
client = 5
instrument = 'EURUSD'
temporality = 1
num_bars = 1
target = 0.00015
type_con = 'forex'

account = 20000
risk = 0.01
mail_1 = "aestrad494@gmail.com"
mail_2 = "ibpy.notifications@gmail.com"
mails = [mail_2]#, mail_2]

## Initializing variables
entry_price_b = 0
entry_price_s = 0
exit_price_b = 0
exit_price_s = 0
mail_buy_entry = False
mail_sell_entry = False
mail_buy_exit = False
mail_sell_exit = False
buy_closed_by_time = False
sell_closed_by_time = False

## Calculating hour and weekday
def calc_times():
    global date, hour, weekday
    date, hour, weekday = ranguito.day_and_hour()

## Allowing Trading
def allowing_trading():
    global allow_trading
    allow_trading = ranguito.allow_trading(hour,weekday)

## Instantiating Classes
ib = IB()
ranguito = Ranguito(instrument,type_con,num_bars,temporality,target,initial_hour,final_hour,client)

## Ib Connection
print(ib.connect('127.0.0.1',7497,client))

## Contract Creation
contract = Forex(instrument)

## Download Historical
historical_0 = ranguito.download_data(ib, contract)
historical = util.df(historical_0).set_index('date')
historical.drop(['volume','average','barCount'], axis = 1, inplace = True)

def hist_to_df():
    global historical
    historical = util.df(historical_0).set_index('date')
    historical.drop(['volume','average','barCount'], axis = 1, inplace = True)
    return(historical)

## Range Calculation
hour_range = pd.to_datetime(initial_hour) + timedelta(minutes = num_bars*temporality)

def max_min_lots():
    global allow_trading
    global maximum, minimum, lots
    maximum, minimum, lots = ranguito.max_and_min(historical, date, 5, account, risk)

## Send Orders
hour_orders = pd.to_datetime(hour_range) + timedelta(seconds = 1)

def send_orders():
    global id_buy, id_sell
    global id_buy_entry, id_sell_entry
    global margin_entry_buy, margin_entry_sell
    global orders_buy, orders_sell
    id_buy, orders_buy, margin_entry_buy = ranguito.bracket_stop_order(ib, 'BUY', lots, contract, maximum, maximum + target, minimum)
    id_buy_entry = id_buy[0]
    id_sell, orders_sell, margin_entry_sell = ranguito.bracket_stop_order(ib, 'SELL', lots, contract, minimum, minimum - target, maximum)
    id_sell_entry = id_sell[0]

## Entry Values
def calc_entry_values():
    global entry_price_b, entry_price_s
    global commission_entry_buy, commission_entry_sell
    if pd.to_datetime(hour) > pd.to_datetime(str(hour_range)):
        if historical['high'][-1] > maximum:
            commission_entry_buy, entry_price_b = ranguito.order_values(util.tree(ib.fills()), id_buy_entry, lots)
        if historical['low'][-1] < minimum:
            commission_entry_sell, entry_price_s = ranguito.order_values(util.tree(ib.fills()), id_sell_entry, lots)

## Exit Values
def calc_exit_values():
    global exit_price_b, exit_price_s
    global commission_exit_buy, commission_exit_sell
    global profit_s, profit_b
    if pd.to_datetime(hour) > pd.to_datetime(str(hour_range)) and id_sell_entry > 0:
        id_list = [id_buy[1],id_buy[2],id_sell[1],id_sell[2]]
        id_sell_exit, id_buy_exit = ranguito.filled_id(util.tree(ib.fills()), id_list)
        if not sell_closed_by_time:
            commission_exit_buy, exit_price_b, profit_s = ranguito.order_values(util.tree(ib.fills()), id_buy_exit, lots, True)
        if not buy_closed_by_time:
            commission_exit_sell, exit_price_s, profit_b = ranguito.order_values(util.tree(ib.fills()), id_sell_exit, lots, True)

## Final Profit
def calc_final_profit():
    global profit_buy, profit_sell
    if pd.to_datetime(hour) > pd.to_datetime(str(hour_range)):
        if (entry_price_b > 0) and (exit_price_s > 0):
            profit_buy = round(((exit_price_s - entry_price_b) * lots) - commission_entry_buy - commission_exit_sell,2)
        if (entry_price_s > 0) and (exit_price_b > 0):
            profit_sell = round(((entry_price_s - exit_price_b) * lots) - commission_entry_sell - commission_exit_buy,2)

## Close Orders
def cancel_orders():
    global exit_price_b, exit_price_s
    global id_sell_exit, id_buy_exit
    global buy_closed_by_time, sell_closed_by_time 
    global commission_exit_buy, commission_exit_sell
    
    if(entry_price_b == 0):
        ib.cancelOrder(orders_buy.parent)
    else:
        if(exit_price_s == 0):
            ib.cancelOrder(orders_buy.stopLoss)
            buy_closed_by_time = True
            id_sell_exit, margin_sell_exit = ranguito.order_send(ib, 'SELL', lots, contract)
            commission_exit_sell, exit_price_s, profit_b = ranguito.order_values(util.tree(ib.fills()), id_sell_exit, lots, True)
    
    if(entry_price_s == 0):
        ib.cancelOrder(orders_sell.parent)
    else:
        if(exit_price_b == 0):
            ib.cancelOrder(orders_sell.stopLoss)
            sell_closed_by_time = True
            id_buy_exit, margin_buy_exit = ranguito.order_send(ib, 'BUY', lots, contract)
            commission_exit_buy, exit_price_b, profit_s = ranguito.order_values(util.tree(ib.fills()), id_buy_exit, lots, True)

## Send emails
def sending_emails():
    global mail_buy_entry, mail_sell_entry, mail_buy_exit, mail_sell_exit
    #Mail for entries
    if (entry_price_b > 0) and not mail_buy_entry:
        subject_entry_buy = 'Entry Buy Notification: Ranguito'
        msg_entry_buy = 'Buy Opened in ' + str(instrument) + '\nPrice: ' + str(entry_price_b) +                        '\nLots: ' + str(lots) + '\nReq.Margin(ib): ' + str(margin_entry_buy) +                        '\nAt: ' + str(hour)
        ranguito.send_email(subject_entry_buy, msg_entry_buy, mails)
        mail_buy_entry = True
    if (entry_price_s > 0) and not mail_sell_entry:  
        subject_entry_sell = 'Entry Sell Notification: Ranguito'
        msg_entry_sell = 'Sell Opened in ' + str(instrument) + '\nPrice: ' + str(entry_price_s) +                         '\nLots: ' + str(lots) + '\nReq.Margin(ib): ' + str(margin_entry_sell) +                         '\nAt: ' + str(hour)
        ranguito.send_email(subject_entry_sell, msg_entry_sell, mails)
        mail_sell_entry = True
    
    #Mail for exits
    if mail_buy_entry and (exit_price_s > 0) and not mail_buy_exit :
        subject_exit_buy = 'Exit Buy Notification: Ranguito'
        msg_exit_buy = 'Buy Closed in ' + str(instrument) + '\nPrice: ' + str(exit_price_s) +                       '\nProfit(USD): ' + str(profit_buy) +                       '\ncommissions: ' + str(commission_entry_buy + commission_exit_sell) +                       '\nAt: ' + str(hour)
        ranguito.send_email(subject_exit_buy, msg_exit_buy, mails)
        mail_buy_exit = True
    if mail_sell_entry and (exit_price_b > 0) and not mail_sell_exit :
        subject_exit_sell = 'Exit Sell Notification: Ranguito'
        msg_exit_sell = 'Sell Closed in ' + str(instrument) + '\nPrice: ' + str(exit_price_b) +                        '\nProfit(USD): ' + str(profit_sell) +                        '\ncommissions: ' + str(commission_entry_sell + commission_exit_buy) +                        '\nAt: ' + str(hour)
        ranguito.send_email(subject_exit_sell, msg_exit_sell, mails)
        mail_sell_exit = True

## Scheduling Functions
### - Each second Threading
def back_1():
    while True:
        calc_times()
        allowing_trading()
        hist_to_df()
        sleep(1)
threading.Thread(name='background', target=back_1).start()

### - Each ten seconds scheduler
if __name__ == '__main__':
    # Instantiating Scheduler
    sched = BackgroundScheduler()
    sched.start()

    ### - Fixed time
    ib.schedule(pd.to_datetime(str(hour_range)), max_min_lots)
    ib.schedule(pd.to_datetime(str(hour_orders)), send_orders)
    ib.schedule(pd.to_datetime(final_hour), cancel_orders)
    
    ### - Continuous
    sched.add_job(calc_entry_values,trigger = 'interval', seconds = 1)
    sched.add_job(calc_exit_values,trigger = 'interval', seconds = 1)
    sched.add_job(calc_final_profit,trigger = 'interval', seconds = 1)
    sched.add_job(sending_emails,trigger = 'interval', seconds = 10)

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            #ib.sleep(1)
            util.sleep(1)
            #asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        # Not strictly necessary if daemonic mode is enabled but should be done if possible
        sched.shutdown()