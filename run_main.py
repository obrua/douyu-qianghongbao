
import sys
import os
import signal
import requests
import json
import queue
import time
import threading
from threading import Thread
from gethongbao import verControl, HongBao, QiangHongBao, get_cookie, update_cookie
from basemodule.logger import logger
from douyu_login import utils as login_utils
from basemodule.config import Config, BASE_DIR

bEXIT = False


def quit(signum, frame):
    global bEXIT
    logger.warning('消息获取: 强制退出')
    bEXIT = True


if __name__ == '__main__':

    signal.signal(signal.SIGINT, quit)
    signal.signal(signal.SIGTERM, quit)

    verControl()

    logger.level("HONGBAO", no=50, color="<red>", icon="🧧") 
    hongbao_logfile = os.environ.get('HONGBAO_LOGFILE') or 'hongbao.log'
    logger.log("HONGBAO", '抢到礼物立即自动赠送[{}] (火箭、飞机除外)', '开启' if Config.AUTO_SEND else '关闭')
    logger.log("HONGBAO", '红包的记录文件: {}', os.path.join(BASE_DIR, hongbao_logfile))
    logger.log("HONGBAO", '格式: unix时间 房间名 房间号 礼物名')
    logger.add(os.path.join(BASE_DIR, hongbao_logfile),
            format="<g>{time}</> - <lvl>{message}</>",
            level="HONGBAO",
            enqueue=True,
            rotation="50 MB",
            encoding='utf-8')


    cookie_douyu = get_cookie()
    acf_uid , acf_nickname = login_utils.get_uidAndname(cookie_douyu)
    logger.success(f'账号: {acf_nickname}({acf_uid})')
    os.system(f"title 账号: {acf_nickname}({acf_uid}) - Powered by obrua.com")

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

        logger.info('检查内容: {} [{} {}] [{} {}]', nowThreadsName, 
            hongbao_service, hongbao_service.get_done() if hongbao_service else 'none', 
            qiang_service, qiang_service.get_done() if qiang_service else 'none')
            
        isxuqi = False
        if hongbao_service and hongbao_service.get_overcookie():
            logger.warning('cookie过期, 续期cookie并重启服务')
            if hongbao_service:
                hongbao_service.stop()
            if qiang_service:
                qiang_service.stop()

            # 重新获取cookie
            cookie_douyu = update_cookie(cookie_douyu)
            if not cookie_douyu:
                logger.error('cookie续期失败, 请重启重新扫码登录')
                break
                time.sleep(5)

            acf_uid , acf_nickname = login_utils.get_uidAndname(cookie_douyu)
            isxuqi = True


        if not isxuqi and 'HongBao-do' not in nowThreadsName:
            logger.error('红包监控线程丢失')
            if hongbao_service:
                hongbao_service.stop()
                logger.error('停止服务 准备重启')
                time.sleep(10)

        if not isxuqi and 'HongBao-qiang' not in nowThreadsName:
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
