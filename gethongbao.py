# cython: language_level=3
import sys
import os
import signal
from dotenv import load_dotenv
import loguru
import time
from datetime import datetime
import random
import threading
import ntplib
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import requests
import json
import re
import queue
from basemodule.logger import logger
from basemodule.config import Config, BASE_DIR
from douyu_login import utils as login_utils
from douyu_login import loginByQrcode

start_unixtime = time.time()

def get_aliyuntime(offset=0.4):
    '''获取阿里云与本地时间的差值'''
    tx_time = 0
    try:
        ntp_aliyun = ['ntp1.aliyun.com', 'ntp2.aliyun.com', 'ntp3.aliyun.com', 'ntp4.aliyun.com', 'ntp5.aliyun.com', 'ntp6.aliyun.com', 'ntp7.aliyun.com']

        ntp_client = ntplib.NTPClient()
        ntp_stats = ntp_client.request(random.choice(ntp_aliyun))
        tx_time = time.time() - ntp_stats.tx_time
    finally:
        return  tx_time - offset

class HongBao():
    def __init__(self, _queue, cookie_douyu, stock_hongbao, got_hongbao, qiang):
        self.__queue = _queue
        self.__done = False
        self.__overcookie = False
        self.__cookie_douyu = cookie_douyu
        # list []
        self.__stock_hongbao = stock_hongbao
        # set
        self.__got_hongbao = got_hongbao
        self.starttime = int(time.time())
        self.qiang = qiang
        self._init_run()

    def _init_run(self):
        """启动监控红包&红包结果监控线程"""
        do_hongbao = Thread(target=self._do_hongbao,
                            name="HongBao-do")
        do_hongbao.start()

    def stop(self):
        """关闭"""
        logger.warning('stop 关闭 HongBao')
        self.__done = True

    def get_done(self):
        return self.__done

    def set_overcookie(self):
        """设置cookie过期"""
        self.__overcookie = True

    def get_overcookie(self):
        return self.__overcookie

    def _do_hongbao(self):
        while True:

            i_propredpacket = self._get_propredpacket()
            i_hongbaores = self._get_hongbaores()
            if i_hongbaores == -401:
                self.set_overcookie()
                self.stop()

            logger.success('红包监控中..')
            logger.debug(f'当前已监控到的红包： {self.__stock_hongbao}')
            logger.debug(f'当前已抢到的红包： {self.__got_hongbao}')

            for i in range(10):
                if self.__done:
                    break
                time.sleep(2)

            if self.__done:
                break

    def _get_hongbaores(self):
        try:
            url = 'https://www.douyu.com/japi/interactnc/web/propredpacket/get_prp_records?type_id=1'
            res = requests.get(url, cookies=self.__cookie_douyu).json()
            if res['error']==1002:
                logger.error(f'cookie过期 {res}')
                return -401

            data = res['data']['list']
            logger.trace(data)
            for item in data:
                item.pop('vsrc')
                jsonStr = json.dumps(item, ensure_ascii=False)  # dump后中文编码不变
                if jsonStr not in self.__got_hongbao and item['time'] > start_unixtime:
                    self.__got_hongbao.add(jsonStr)
                    logger.info(f'新抢到红包：{jsonStr}')
                    self.updata(item)
                    logger.log("HONGBAO", " {} {} {} {}",
                               item['time'], item['rid'], item['nn'], item['prpn'])
                    if Config.AUTO_SEND:
                        time.sleep(5)
                        self.songliwu(item)
                    # print(item['rid'],item['nn'],item['prpn'])
        except Exception as e:
            logger.exception(f'_get_hongbaores {e}')
            return -1
        else:
            return 99

    def _get_propredpacket(self):
        try:
            url = 'https://www.douyu.com/japi/interactnc/web/propredpacket/getPrpList?type_id=2&room_id=9999'
            _list = []
            _fanslist=self.get_fanslist()
            res = requests.get(url)
            data = res.json()
            data = data['data']['list']
            for item in data:
                datas = {}
                datas['stmap'] = item['startTime']
                datas['tiaojian'] = item['joinc']
                datas['roomid'] = item['rid']
                datas['activityid'] = item['activityid']
                if item['joinc'] <= 1 or str(datas['roomid']) in _fanslist:
                    _list.append(datas)

            logger.debug(f'get_propredpacket {_list}')

            for item in _list:
                if item['activityid'] not in self.__stock_hongbao:
                    logger.info('监控到新红包：{} {} {} {} {}'.format(datetime.fromtimestamp(item['stmap']).strftime(
                        '%Y-%m-%d %H:%M:%S'), item['stmap'], item['roomid'], item['tiaojian'], item['activityid']))
                    self.__stock_hongbao.append(item['activityid'])

                    if datas['stmap'] <= int(time.time()):
                        logger.info('立即启动抢红包')
                        self.qiang.qiang(item)
                    else:
                        logger.info('将该红包加入待抢队列')
                        self.__queue.put(item)
        except Exception as e:
            logger.exception(f'_get_propredpacket {e}')
            return -1
        else:
            return 99

    def get_fanslist(self):
        try:
            url='https://www.douyu.com/member/cp/getFansBadgeList'
            res=requests.get(url,cookies=self.__cookie_douyu)
            html=res.text
            __list=re.findall('data-fans-room="(\d+?)"',html)
            return __list 
        except Exception as e:
            logger.exception('fanslist: {}'.format(e))

    def songliwu(self, item):
        try:
            prid = {'666': 978, '大气': 975, '办卡': 974}
            url = 'https://www.douyu.com/japi/prop/donate/mainsite/v1'
            header = {'user-agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
                      'content-type': 'application/x-www-form-urlencoded',
                      'referer': 'https://www.douyu.com/%s' % item['rid']}

            i = item['prpn']
            if i not in prid:
                pass
            else:
                payload = 'propId=%s&propCount=1&roomId=%s&bizExt=\{"yzxq":\{\}\}' % (
                    prid[i], item['rid'])
                res = requests.post(
                    url, payload, headers=header, cookies=self.__cookie_douyu).json()
                if res['error'] == 0:
                    logger.success('{} 自动赠送成功！', i)
                    logger.log("HONGBAO", " {} {} {} {} 自动赠送成功！",
                               item['time'], item['rid'], item['nn'], item['prpn'])

                else:
                    logger.error('{} 自动赠送错误：{}', i, res['msg'])

        except Exception as e:
            logger.exception('songliwu: {}'.format(e))
        finally:
            pass

    def updata(self, item):
        try:
            acf_uid, acf_nickname = login_utils.get_uidAndname(
                self.__cookie_douyu)

            baseheaders = {
                'referer': 'https://www.obrua.com/dy_box',
                'origin': 'https://www.obrua.com',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36',
            }
            url = 'https://www.obrua.com/backA/api/dy_box'

            with requests.Session() as s:
                paramjson = {
                    'itype': 2,
                    'roomid': item['rid'],
                    'uid': acf_uid,
                    'nickname': acf_nickname,
                    'time': item['time'],
                    'stype': item['prpn'],
                    'count': item['pnum']
                }
                res = s.post(url, headers=baseheaders,
                             data=None, json=paramjson)
        except Exception as e:
            logger.exception('updata: {}'.format(e))
        finally:
            pass


class QiangHongBao():
    def __init__(self, _queue, cookie_douyu, threadNum):
        self.__queue = _queue
        self.__done = False
        self.__cookie_douyu = cookie_douyu
        self.__qianglist = []
        self.__followlist = []
        self.threadpool_doqiang = ThreadPoolExecutor(threadNum, thread_name_prefix='qiang_')

        self._init_run()

    def stop(self):
        """关闭线程"""
        logger.warning('stop 关闭 QiangHongBao')
        self.__done = True

    def get_done(self):
        return self.__done

    def _init_run(self):
        """启动监控红包&红包结果监控线程"""
        self.__followlist=self._get_followlist()
        qiang_hongbao = Thread(target=self._qiang_hongbao,
                               name="HongBao-qiang")
        qiang_hongbao.start()

    def _get_followlist(self):
        url='https://www.douyu.com/wgapi/livenc/liveweb/follow/list?sort=0&cid1=0'
        __followlist=[]
        try:
            data=requests.get(url,cookies=self.__cookie_douyu).json()
            #print(data)
            if data['error']==0:
                followlist=data['data']['list']
                for item in followlist:
                    __followlist.append(item['room_id'])
                logger.info('获取关注列表成功 关注主播数量为{}个',len(__followlist))
                return __followlist
        except Exception as e:
            logger.exception(f'get_followlist {e}')

    def _qiang_call_back(self, futures):
        response = futures.result()
        logger.info("抢红包线程结束 {} {}", futures, response)

    def _qiang_hongbao(self):
        while True:
            _list = []
            while not self.__queue.empty():
                item = self.__queue.get()  # 获取任务
                # [{'stmap': 1576734833, 'tiaojian': 1, 'roomid': 7082697, 'activityid': 4272}]
                try:
                    it = int(item['stmap'])-int(time.time())
                except:
                    it = 9999

                if it < 30:
                    logger.info("开启抢红包线程 {} {}", item, time.time())
                    f = self.threadpool_doqiang.submit(self.qiang, item=item)
                    f.add_done_callback(self._qiang_call_back)
                else:
                    logger.debug("还未开始 {} {}", item, time.time())
                    _list.append(item)

            for item in _list:
                self.__queue.put(item)

            for i in range(5):
                if self.__done:
                    break
                time.sleep(2)

            if self.__done:
                break

    def qiang(self, item):
        try:
            roomid = item['roomid']

            difftime = get_aliyuntime()
            logger.info('时间同步差值: {}', difftime)
            if item['tiaojian'] >= 1:
                self.guanzhu(roomid)
                while True:
                    timestmap = int(time.time() - difftime)
                    #logger.info('qiang {} {}', timestmap, item['stmap'])
                    if timestmap >= item['stmap']:
                        state = self.grab_prp(item=item)
                        # print('请求时间为%s'%timestmap,state)
                        logger.info(
                            '请求时间为：{} 获取状态为：{}'.format(timestmap, state))
                        if state != 2:
                            if state == 1:
                                logger.info(f'抢红包成功')
                            if state == 0:
                                logger.info(f'抢红包失败，红包已空')
                            
                            if state == -401:
                                # 直接停止
                                self.stop()

                            time.sleep(1)
                            # self.__stock_hongbao.remove(item['activityid'])
                            break
                    time.sleep(0.1)
                if roomid not in self.__followlist:
                    self.quguan(roomid)
                else:
                    logger.info(f'已经关注，无需取关')
            else:
                # print('条件：全部水友参与')
                logger.info(f'条件为全部水友参与，无需关注')
                while True:
                    timestmap = int(time.time() - difftime)
                    if timestmap >= item['stmap']:
                        time.sleep(0.3)
                        state = self.grab_prp(item=item)
                        # print('请求时间为%s'%timestmap,state)
                        logger.info(
                            '请求时间为：{} 获取状态为：{}'.format(timestmap, state))
                        if state != 2:
                            if state == 1:
                                logger.info(f'抢红包成功')
                            if state == 0:
                                logger.info(f'抢红包失败，红包已空')
                            time.sleep(1)
                            # self.__stock_hongbao.remove(item['activityid'])
                            break

        except Exception as e:
            logger.exception(f'qiang {e}')
            return {'res':-1, 'stmap': item['stmap']}
        else:
            return {'res':99, 'stmap': item['stmap']}

    def grab_prp(self, item):
        try:
            activityid = item['activityid']
            url = 'https://www.douyu.com/japi/interactnc/web/propredpacket/grab_prp'
            header = {'user-agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
                      'content-type': 'application/x-www-form-urlencoded',
                      'referer': 'https://www.douyu.com/%s' % item['roomid'],
                      'TE': 'Trailers'}
            data = 'activityid=%s&ctn=%s' % (
                activityid, self.__cookie_douyu['acf_ccn'])
            res = requests.post(url, data, headers=header,
                                cookies=self.__cookie_douyu).json()
            # print(res)
            if res['error']==1002:
                logger.error(f'cookie过期 {res}')

                return -401

            return res['data']['isSuc']
        except Exception as e:
            logger.exception(f'_grab_prp {e}')
            return -1
        else:
            return 99

    def guanzhu(self, roomid):
        try:
            url = 'https://www.douyu.com/room/follow/add_confuse/%s' % roomid
            payload = 'room_id=%s' % roomid
            header = {'user-agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
                      'content-type': 'application/x-www-form-urlencoded',
                      'referer': 'https://www.douyu.com/%s' % roomid}
            html = requests.post(url, payload, headers=header,
                                 cookies=self.__cookie_douyu).json()
            logger.info(f'关注成功：{html}')
        except Exception as e:
            logger.exception(f'_guanzhu {e}')
            return -1
        else:
            return 99

    def quguan(self, roomid):
        try:
            url = 'https://www.douyu.com/room/follow/cancel_confuse/%s' % roomid
            payload = 'room_id=%s' % roomid
            header = {'user-agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
                      'content-type': 'application/x-www-form-urlencoded',
                      'referer': 'https://www.douyu.com/%s' % roomid}
            html = requests.post(url, payload, headers=header,
                                 cookies=self.__cookie_douyu).json()
            # print('取关成功',html)
            logger.info(f'取关成功：{html}')
        except Exception as e:
            logger.exception(f'_quguan {e}')
            return -1
        else:
            return 99


def get_cookie(flag=0):
    # 从文件获取cookie
    cookie_douyu = loginByQrcode.get_cookie_from_txt()
    if cookie_douyu and loginByQrcode.test_get_csrf_cookie(cookie_douyu):
        logger.success('cookie有效.')
        # 重新从文件取
        cookie_douyu = loginByQrcode.get_cookie_from_txt()
        return cookie_douyu
    elif cookie_douyu and flag == 0:
        if loginByQrcode.refresh_cookie(cookie_douyu):
            logger.success('cookie更新成功.')
            return get_cookie(flag=2)
        else:
            while not loginByQrcode.pc_qrcode_login():
                logger.success('二维码登录失败, 重试.')
            return get_cookie()
    else:
        # 二维码登录
        if flag != 1:
            while not loginByQrcode.pc_qrcode_login():
                logger.success('二维码登录失败, 重试.')
            return get_cookie()
        else:
            # flag=1时, 不执行登录
            return None


def update_cookie(cookie):
    if loginByQrcode.refresh_cookie(cookie):
        logger.success('cookie更新成功.')
        return get_cookie(flag=1)
    else:
        return None


def verControl():

    version = '1.0.2.0'

    print('=============================================================')
    print('            此工具由obrua.com提供 by 胖头鱼的机器人 && 小丑')
    print('                 发布地址: https://www.obrua.com')
    print(f'                  当前版本: v{version}')
    print('=============================================================')

    url = 'https://www.obrua.com/913boxAssistant/version'
    headers = {
        'Accept-Language': 'zh-CN',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.81 Safari/537.36'
    }
    redata = {}
    bcontinue = True
    try:
        req = requests.get(url, headers=headers)
        redata = req.json()
        req.close
    except:
        print('            获取版本号失败,请确保能正常上网')
        bcontinue = False

    if 'qianghongbao' in redata:
        if version < redata['qianghongbao']:
            bcontinue = False
            print('                  最新版本: v{}'.format(redata['qianghongbao']))
            print('            请更新: https://www.obrua.com')

    # os.system("pause")
    if not bcontinue:
        sys.exit()
