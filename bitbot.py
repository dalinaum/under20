import time, datetime
import requests, json
import sys
import base64, hmac, hashlib
import logging

if not ('logger' in globals()):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler('bitbot.log')
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())

API_HOST = "https://api.gopax.co.kr"
API_KEY = "XXX"
SECRET_KEY = "YYY"

yesterday = datetime.datetime.now() - datetime.timedelta(days = 1)
yesterday_begin = datetime.datetime(yesterday.year, yesterday.month, yesterday.day,0,0,0,0)
yesterday_begin_time = int(time.mktime(yesterday_begin.timetuple()) * 1000.0)
yesterday_end = datetime.datetime(yesterday.year, yesterday.month, yesterday.day,23,59,59,999)
yesterday_end_time = int(time.mktime(yesterday_end.timetuple()) * 1000.0)

def logResponse(response):
    logger.info("status_code: " + str(response.status_code))
    logger.info("\nheaders: " + str(response.headers))
    logger.info("\ntext: " + response.text)

def assets():
    url = API_HOST + "/assets"
    response = requests.get(url)
    if response.status_code != 200:
        logResponse(response)
        return
    return json.loads(response.text)

def candles(pair_name, start = yesterday_begin_time, end = yesterday_end_time, interval = 30):
    url = f"{API_HOST}/trading-pairs/{pair_name}/candles?start={start}&end={end}&interval={interval}"
    response = requests.get(url)
    if response.status_code != 200:
        logResponse(response)
        return
    parsed = json.loads(response.text)
    result = { 'start' : parsed[0][0], 'end' : parsed[-1][0], 'open' : parsed[0][3], 'close' : parsed[-1][4] }
    min = sys.maxsize
    max = -sys.maxsize - 1

    for item in parsed:
        item_min = item[1]
        item_max = item[2]
        if item_min < min:
            min = item_min
        if item_max > max:
            max = item_max

    result['low'] = min
    result['high'] = max
    result['range'] = max - min
    result['signal_range'] = abs(result['close'] - result['open'])
    result['noise'] = result['signal_range'] / result['range']
    result['breakout'] = (result['range'] * result['noise']) + result['close']
    result['volatility'] = result['range'] / result['close']
    return result

def prices(pair_name):
    url = f"{API_HOST}/trading-pairs/{pair_name}/book"
    response = requests.get(url)
    if response.status_code != 200:
        logResponse(response)
        return
    return json.loads(response.text)

def prices_ask(pair_name):
    return prices(pair_name)['ask']

def prices_bid(pair_name):
    return prices(pair_name)['bid']

def price_lowest_ask(pair_name):
    (id, price, volume) = prices_ask(pair_name)[0]
    return { 'id' : id, 'price' : price, 'volume' : volume }

def price_highest_bid(pair_name):
    (id, price, volume) = prices_bid(pair_name)[0]
    return { 'id' : id, 'price' : price, 'volume' : volume }

def generate_signature(nonce, method, request_path, body = ''):
    what = nonce + method + request_path + body
    key = base64.b64decode(SECRET_KEY)
    signature = hmac.new(key, what.encode("utf8"), hashlib.sha512)
    return base64.b64encode(signature.digest())

def get_nonce():
    return str(time.time())

def generate_headers(method, request_path, body = ''):
    nonce = get_nonce()
    signature = generate_signature(nonce, method, request_path, body)
    return {
        'API-KEY': API_KEY,
        'SIGNATURE': signature,
        'NONCE': nonce
    }

def balances():
    method = 'GET'
    request_path = '/balances'
    headers = generate_headers(method, request_path)
    url = f"{API_HOST}{request_path}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logResponse(response)
        return
    return json.loads(response.text)

def balance(pair_name):
    method = 'GET'
    request_path = f"/balances/{pair_name}"
    headers = generate_headers( method, request_path)
    url = f"{API_HOST}{request_path}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logResponse(response)
        return
    return json.loads(response.text)

def buy(pair_name, price, amount):
    method = 'POST'
    # type market 안된다. 미친 고팍스
    body = {
        'type' : 'limit',
        'side' : 'buy',
        'price' : price,
        'amount' : amount,
        'tradingPairName' : pair_name
    }
    data = json.dumps(body)
    request_path = "/orders"
    headers = generate_headers(method, request_path, data)
    url = f"{API_HOST}{request_path}"
    response = requests.post(url, headers=headers, data=data)
    if response.status_code != 200:
        logResponse(response)
        return
    return json.loads(response.text)

def buy_market(pair_name, sum):
    price_map = price_lowest_ask(pair_name)
    price = price_map['price']
    amount = sum / price
    return buy(pair_name, price, amount)

def explain_candles(name, candles):
    logger.info(f"{name}\n\t어제 시초가:{candles['open']} / 종가:{candles['close']} / 저가:{candles['low']} / 고가:{candles['high']}")
    logger.info(f"\t변동폭:{candles['range']} / 노이즈:{candles['noise']}  / 목표금액:{candles['breakout']} / 변동성:{candles['volatility']}")

def breakout():
    total_money = balance('KRW')['avail']
    money = total_money / 3
    logger.info(f"잔고: {total_money} / 개별 투자 금액: {money}")

    buy_eth = False
    buy_btc = False
    buy_xrp = False

    eth = candles('ETH-KRW')
    btc = candles('BTC-KRW')
    xrp = candles('XRP-KRW')
    explain_candles('ETH', eth)
    explain_candles('BTC', btc)
    explain_candles('XRP', xrp)

    target_eth_price = eth['breakout']
    target_btc_price = btc['breakout']
    target_xrp_price = xrp['breakout']
    logger.info(f"목표 금액은 ETH: {target_eth_price} / BTC: {target_btc_price} / XRP: {target_xrp_price}")

    target_volatility = 0.02
    sum_eth = target_volatility / eth['volatility'] * money
    sum_btc = target_volatility / btc['volatility'] * money
    sum_xrp = target_volatility / xrp['volatility'] * money
    logger.info(f"이번 투자 금액은 ETH: {sum_eth} / BTC: {sum_btc} / XRP: {sum_xrp}")

    logger.info("가격 변동 추적을 시작합니다.")
    while True:
        if buy_eth == True and buy_btc == True and buy_xrp == True:
            logger.info("더 이상 처리할게 없습니다.")
            break

        if buy_eth == False:
            try:
                eth_price = price_lowest_ask('ETH-KRW')['price']
                logger.info(f"ETH 현재: {eth_price} 목표: {target_eth_price}")
                if (eth_price >= target_eth_price):
                    logger.info("ETH 구매합니다.")
                    logger.info(buy_market('ETH-KRW', sum_eth))
                    buy_eth = True
            except Exception as ex:
                logger.error('ETH 에러가 발생했습니다.')
                logger.exception(ex)
                time.sleep(30)

        if buy_btc == False:
            try:
                btc_price = price_lowest_ask('BTC-KRW')['price']
                logger.info(f"BTC 현재: {btc_price} 목표: {target_btc_price}")
                if (btc_price >= target_btc_price):
                    logger.info("BTC 구매합니다.")
                    logger.info(buy_market('BTC-KRW', sum_btc))
                    buy_btc = True
            except Exception as ex:
                logger.error('BTC 에러가 발생했습니다.')
                logger.exception(ex)
                time.sleep(30)

        if buy_xrp == False:
            try:
                xrp_price = price_lowest_ask('XRP-KRW')['price']
                logger.info(f"XRP 현재: {xrp_price} 목표: {target_xrp_price}")
                if (xrp_price >= target_xrp_price):
                    logger.info("XRP 구매합니다.")
                    logger.info(buy_market('XRP-KRW', sum_xrp))
                    buy_xrp = True
            except Exception as ex:
                logger.error('XRP 에러가 발생했습니다.')
                logger.exception(ex)
                time.sleep(30)

        time.sleep(3)
