# from douyu_login import loginByQrcode
# cookie_douyu = loginByQrcode.get_cookie_from_txt()
# loginByQrcode.refresh_cookie(cookie_douyu)
import time
import ntplib
import random

ntp_aliyun = ['ntp1.aliyun.com', 'ntp2.aliyun.com', 'ntp3.aliyun.com', 'ntp4.aliyun.com', 'ntp5.aliyun.com', 'ntp6.aliyun.com', 'ntp7.aliyun.com']

ntp_client = ntplib.NTPClient()
ntp_stats = ntp_client.request(random.choice(ntp_aliyun))
print(ntp_stats.tx_time,time.time())
tx_time = ntp_stats.tx_time
tx_time = time.time() - tx_time
print(tx_time)