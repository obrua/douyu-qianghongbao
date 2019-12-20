import sys
import os
import signal
from dotenv import load_dotenv
import loguru
import time
from datetime import datetime
import random
import threading
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import requests
import json
import re
import queue
from basemodule.logger import logger
from douyu_login import loginByQrcode
from douyu_login import utils as login_utils
from basemodule.config import Config, BASE_DIR

start_unixtime = time.time()

logger.level("HONGBAO", no=50, color="<red>", icon="🧧")
hongbao_logfile = os.environ.get('HONGBAO_LOGFILE') or 'hongbao.log'
logger.log("HONGBAO", '红包的记录文件: {}', os.path.join(BASE_DIR, hongbao_logfile))
logger.log("HONGBAO", '格式: unix时间 房间名 房间号 礼物名')
logger.add(os.path.join(BASE_DIR, hongbao_logfile),
           format="<g>{time}</> - <lvl>{message}</>",
           level="HONGBAO",
           enqueue=True,
           rotation="50 MB",
           encoding='utf-8')

bEXIT = False


def quit(signum, frame):
    global bEXIT
    logger.warning('消息获取: 强制退出')
    bEXIT = True


class HongBao():
    def __init__(self, _queue, cookie_douyu, stock_hongbao, got_hongbao, qiang):
        self.__queue = _queue
        self.__done = False
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

    def _do_hongbao(self):
        while True:

            i_propredpacket = self._get_propredpacket()
            i_hongbaores = self._get_hongbaores()

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
            res = requests.get(url)
            data = res.json()
            data = data['data']['list']
            for item in data:
                datas = {}
                datas['stmap'] = item['startTime']
                datas['tiaojian'] = item['joinc']
                datas['roomid'] = item['rid']
                datas['activityid'] = item['activityid']
                if item['joinc'] <= 1:
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

    def updata(self, item):
        try:
            acf_uid , acf_nickname = login_utils.get_uidAndname(self.__cookie_douyu)

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
                    'stype': item['prpn'],
                    'count': item['pnum']
                }
                res = s.post(url, headers=baseheaders, data=None, json=paramjson)
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
        self.threadpool_doqiang = ThreadPoolExecutor(threadNum)

        self._init_run()

    def stop(self):
        """关闭线程"""
        logger.warning('stop 关闭 QiangHongBao')
        self.__done = True

    def get_done(self):
        return self.__done

    def _init_run(self):
        """启动监控红包&红包结果监控线程"""
        qiang_hongbao = Thread(target=self._qiang_hongbao,
                               name="HongBao-qiang")
        qiang_hongbao.start()

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
                    self.threadpool_doqiang.submit(self.qiang, item=item)
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
            #logger.info('qiang {}', item)
            if item['tiaojian'] == 1:
                self.guanzhu(roomid)
                while True:
                    timestmap = int(time.time())
                    #logger.info('qiang {} {}', timestmap, item['stmap'])
                    if timestmap >= item['stmap']:
                        time.sleep(0.1)
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
                    time.sleep(0.1)
                self.quguan(roomid)
            else:
                # print('条件：全部水友参与')
                logger.info(f'条件为全部水友参与，无需关注')
                while True:
                    timestmap = int(time.time())
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
            return -1
        else:
            return 99

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


def get_cookie():
    # 从文件获取cookie
    cookie_douyu = loginByQrcode.get_cookie_from_txt()
    if cookie_douyu and loginByQrcode.test_get_csrf_cookie(cookie_douyu):
        logger.success('cookie有效.')
        return cookie_douyu
    else:
        # 二维码登录
        while not loginByQrcode.pc_qrcode_login():
            logger.success('二维码登录失败, 重试.')
        return get_cookie()




if __name__ == '__main__':

    signal.signal(signal.SIGINT, quit)
    signal.signal(signal.SIGTERM, quit)

    cookie_douyu = get_cookie()

    acf_uid , acf_nickname = login_utils.get_uidAndname(cookie_douyu)
    logger.success(f'账号: {acf_nickname}({acf_uid})')

    hongbao_queue = queue.Queue()
    stock_hongbao = []
    got_hongbao = set()
    

    qiang_service = QiangHongBao(_queue=hongbao_queue, cookie_douyu=cookie_douyu, threadNum=6)
    hongbao_service = HongBao(_queue=hongbao_queue, cookie_douyu=cookie_douyu,
                      stock_hongbao=stock_hongbao, got_hongbao=got_hongbao, qiang=qiang_service)
    while True:

        logger.info('服务健康检查...')

        nowThreadsName = []  # 用来保存当前线程名称
        for i in threading.enumerate():
            nowThreadsName.append(i.getName())  # 保存当前线程名称

        if  'HongBao-do' not in nowThreadsName:
            logger.error('红包监控线程丢失')
            if hongbao_service:
                hongbao_service.stop()
                logger.error('停止服务 准备重启')
                time.sleep(10)

        if  'HongBao-qiang' not in nowThreadsName:
            logger.error('抢红包线程丢失')
            if qiang_service:
                qiang_service.stop()
                logger.error('停止服务 准备重启')
                time.sleep(10)


        if qiang_service and qiang_service.get_done():
            # 抢服务中断
            logger.warning('抢服务中断 重启')
            qiang_service = None
            qiang_service = QiangHongBao(_queue=hongbao_queue, cookie_douyu=cookie_douyu, threadNum=6)
        elif not qiang_service:
            # 抢服务不存在
            logger.warning('抢服务丢失 重启')
            qiang_service = QiangHongBao(_queue=hongbao_queue, cookie_douyu=cookie_douyu, threadNum=6)

        if hongbao_service and hongbao_service.get_done():
            # 红包服务中断
            logger.warning('红包服务中断 重启')
            hongbao_service = None
            hongbao_service = HongBao(_queue=hongbao_queue, cookie_douyu=cookie_douyu,
                      stock_hongbao=stock_hongbao, got_hongbao=got_hongbao, qiang=qiang_service)
        elif not hongbao_service:
            # 红包服务中断
            logger.warning('红包服务丢失 重启')
            hongbao_service = HongBao(_queue=hongbao_queue, cookie_douyu=cookie_douyu,
                      stock_hongbao=stock_hongbao, got_hongbao=got_hongbao, qiang=qiang_service)

        if bEXIT:
            if hongbao_service:
                hongbao_service.stop()
            if qiang_service:
                qiang_service.stop()
            break

        for i in range(12*5):
            if bEXIT:
                break
            time.sleep(5)
