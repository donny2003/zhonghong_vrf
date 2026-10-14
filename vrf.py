# -*- coding: utf-8 -*-

import requests
import json
import logging
import time
from paho.mqtt import client as mqtt_client

logging.basicConfig(level=logging.INFO)

# 状态映射字典
STATES = {
    'on': {0: 'OFF', 1: 'ON', 'OFF': 0, 'ON': 1},
    'mode': {0: 'off', 1: 'cool', 2: 'dry', 4: 'fan_only', 8: 'heat',
             'off': 0, 'cool': 1, 'dry': 2, 'fan_only': 4, 'heat': 8},
    'fan': {
        0: 'auto',
        1: 'high',
        2: 'medium',
        3: 'low',
        4: 'low',
        5: 'turbo',
        6: 'silent',
        'auto': 0,
        'high': 1,
        'medium': 2,
        'low': 4,
        'turbo': 5,
        'silent': 6
    }
}

CONFIG = {}
acs = []


def setConfig():
    global CONFIG
    CONFIG = {}
    CONFIG['broker'] = "uniap.pulo.cc"
    CONFIG['port'] = 1883
    CONFIG['gateway'] = "192.168.18.88"
    CONFIG['username'] = "mqtt"
    CONFIG['password'] = "mqtt"


def loadConfig(CONFIG_PATH='/data/options.json'):
    global CONFIG
    CONFIG = {}
    with open(CONFIG_PATH) as fp:
        CONFIG = json.load(fp)
    logging.info(" {0}: Config loaded: {1}".format(
        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), CONFIG))


def connect_mqtt() -> mqtt_client:
    global CONFIG

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logging.info(" {0}: Connected to MQTT Broker!".format(
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))))
        else:
            logging.info(" {0}: Failed to connect, return code {1}\n".format(
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), rc))

    client_id = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
    client = mqtt_client.Client(client_id)
    client.username_pw_set(username=CONFIG['username'], password=CONFIG['password'])
    client.on_connect = on_connect
    client.connect(CONFIG['broker'], int(CONFIG['port']))
    return client


def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        logging.info(" {0}: Received `{1}` from `{2}` topic".format(
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
            msg.payload.decode(), msg.topic))

        try:
            if "homeassistant/climate/zhonghong/" in msg.topic:
                object_id = msg.topic.split('/')[3]
                idx = int(object_id.split('_')[1])
                global acs

                # 查找对应空调，找不到则跳过
                i = None
                for j in range(len(acs)):
                    if acs[j]['idx'] == idx:
                        i = j
                        break
                if i is None:
                    logging.info(" {0}: AC idx {1} not found, skip".format(
                        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), idx))
                    return

                ac = {}
                ac['idx'] = idx
                ac['on'] = acs[i]['on']
                ac['mode'] = acs[i]['mode']
                ac['tempSet'] = acs[i]['tempSet']
                ac['fan'] = acs[i]['fan']

                field = msg.topic.split('/')[-2]
                if field == 'temp':
                    ac['tempSet'] = int(float(msg.payload.decode()))
                else:
                    global STATES
                    ac[field] = STATES[field][msg.payload.decode()]

                if field == 'mode' and msg.payload.decode() == 'off':
                    ac['on'] = 0
                else:
                    ac['on'] = 1

                setAC(ac)

            elif msg.topic == "homeassistant/zhonghong/initialize":
                initializeClimates(client)
        except Exception as e:
            logging.info(" {0}: Exception `{1}`".format(
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), e))

    client.on_message = on_message


def publish(client, topic, msg):
    result = client.publish(topic, msg)
    status = result[0]
    if status == 0:
        logging.info(" {0}: Publish `{1}` to `{2}` topic".format(
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), msg, topic))
    else:
        logging.info(" {0}: Failed to send message to topic {1}".format(
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), topic))


def getACList():
    global CONFIG
    api = 'http://{0}/cgi-bin/api.html?f=17&p={1}'
    i = 0
    acs_temp = []
    while True:
        try:
            r = requests.get(api.format(CONFIG['gateway'], i),
                             auth=('admin', ''),
                             proxies={'http': None, 'https': None})
            msg = json.loads(r.text)
            if msg['err'] == 0 and len(msg['unit']) > 0:
                for m in msg['unit']:
                    acs_temp.append(m)
            else:
                break
        except Exception as e:
            r = str(e)
            if "('Connection aborted.', BadStatusLine('" in r:
                msg = json.loads(r[39:-3])
                if msg['err'] == 0 and len(msg['unit']) > 0:
                    for m in msg['unit']:
                        acs_temp.append(m)
                else:
                    break
        i = i + 1
    return acs_temp


def setAC(ac):
    global CONFIG
    api = "http://{0}/cgi-bin/api.html?f=18&idx={1}&on={2}&mode={3}&tempSet={4}&fan={5}".format(
        CONFIG['gateway'], ac['idx'], ac['on'], ac['mode'], ac['tempSet'], ac['fan'])
    logging.info(" {0}: Set: {1}".format(
        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), api))
    try:
        requests.get(api, auth=('admin', ''),
                     proxies={'http': None, 'https': None})
    except Exception as e:
        msg = str(e)
        if "('Connection aborted.', BadStatusLine('" in msg:
            msg = ''
        else:
            msg = ''


def initializeClimates(client, node_id="zhonghong", component="climate",
                       discovery_prefix="homeassistant"):
    global acs
    acs = getACList()
    for ac in acs:
        object_id = "ac_{0}".format(ac['idx'])
        createClimate(client, object_id)

        # 上报初始状态
        topic = "{0}/{1}/{2}/{3}/mode/state".format(
            discovery_prefix, component, node_id, object_id)
        msg = STATES['mode'][0] if ac['on'] == 0 else STATES['mode'][ac['mode']]
        publish(client, topic, msg)

        topic = "{0}/{1}/{2}/{3}/temp/state".format(
            discovery_prefix, component, node_id, object_id)
        publish(client, topic, int(ac['tempSet']))

        topic = "{0}/{1}/{2}/{3}/cur_temp/state".format(
            discovery_prefix, component, node_id, object_id)
        publish(client, topic, int(ac['tempIn']))

        topic = "{0}/{1}/{2}/{3}/fan/state".format(
            discovery_prefix, component, node_id, object_id)
        msg = STATES['fan'].get(ac['fan'], 'auto')
        publish(client, topic, msg)


def createClimate(client, object_id, name=None, device_class=None, icon=None,
                  temperature_unit="C", node_id="zhonghong",
                  component="climate", discovery_prefix="homeassistant"):
    device = {}
    device["identifiers"] = ["ZhongHong VRF"]
    device["name"] = "ZhongHong VRF"
    device["manufacturer"] = "donny"
    device["model"] = "V100"
    device["sw_version"] = "0.3.1"

    topic = "{0}/{1}/{2}/{3}/config".format(
        discovery_prefix, component, node_id, object_id)

    payload = {}
    payload["device"] = device
    payload["temp_unit"] = temperature_unit
    payload["force_update"] = True

    payload["unique_id"] = "{0}_{1}".format(node_id, object_id)
    # ===== 关键修改：object_id -> default_entity_id，必须带 climate. 前缀 =====
    payload["default_entity_id"] = "climate.{0}_{1}".format(node_id, object_id)

    if icon is not None:
        payload["icon"] = icon
    if device_class is not None:
        payload["device_class"] = device_class

    payload["name"] = "zhonghong_{0}".format(object_id)
    payload["modes"] = ["heat", "cool", "dry", "fan_only", "off"]
    payload["fan_modes"] = ["low", "medium", "high", "turbo"]
    payload["max_temp"] = 29.0
    # min_temp 未设置时 HA 默认为 7，可按需启用
    # payload["min_temp"] = 16.0

    # 注意：HA 2026.4 起 MQTT Climate 已移除 power_command_topic / power_state_topic
    # 开关机由 mode 的 off 控制，无需再配置 power_command_topic
    payload["mode_command_topic"] = "{0}/{1}/{2}/{3}/mode/set".format(
        discovery_prefix, component, node_id, object_id)
    payload["temperature_command_topic"] = "{0}/{1}/{2}/{3}/temp/set".format(
        discovery_prefix, component, node_id, object_id)
    payload["fan_mode_command_topic"] = "{0}/{1}/{2}/{3}/fan/set".format(
        discovery_prefix, component, node_id, object_id)

    payload["mode_state_topic"] = "{0}/{1}/{2}/{3}/mode/state".format(
        discovery_prefix, component, node_id, object_id)
    payload["temperature_state_topic"] = "{0}/{1}/{2}/{3}/temp/state".format(
        discovery_prefix, component, node_id, object_id)
    payload["current_temperature_topic"] = "{0}/{1}/{2}/{3}/cur_temp/state".format(
        discovery_prefix, component, node_id, object_id)
    payload["fan_mode_state_topic"] = "{0}/{1}/{2}/{3}/fan/state".format(
        discovery_prefix, component, node_id, object_id)
    payload["temp_step"] = 1.0

    publish(client, topic, json.dumps(payload))

    # 订阅控制指令
    client.subscribe("{0}/{1}/{2}/{3}/mode/set".format(
        discovery_prefix, component, node_id, object_id))
    client.subscribe("{0}/{1}/{2}/{3}/temp/set".format(
        discovery_prefix, component, node_id, object_id))
    client.subscribe("{0}/{1}/{2}/{3}/fan/set".format(
        discovery_prefix, component, node_id, object_id))


def removeClimate(client, object_id, node_id="zhonghong", component="climate",
                  discovery_prefix="homeassistant"):
    topic = "{0}/{1}/{2}/{3}/config".format(
        discovery_prefix, component, node_id, object_id)
    publish(client, topic, json.dumps(''))


def syncACList(client, node_id="zhonghong", component="climate",
               discovery_prefix="homeassistant"):
    global STATES, acs
    acs_temp = getACList()

    # 数量不一致时重新初始化
    if len(acs_temp) != len(acs):
        initializeClimates(client, node_id, component, discovery_prefix)
        return

    for i in range(len(acs)):
        object_id = "ac_{0}".format(acs[i]['idx'])

        if acs[i]['on'] != acs_temp[i]['on'] or acs[i]['mode'] != acs_temp[i]['mode']:
            acs[i]['on'] = acs_temp[i]['on']
            acs[i]['mode'] = acs_temp[i]['mode']
            topic = "{0}/{1}/{2}/{3}/mode/state".format(
                discovery_prefix, component, node_id, object_id)
            msg = STATES['mode'][0] if acs[i]['on'] == 0 else STATES['mode'][acs[i]['mode']]
            publish(client, topic, msg)

        if acs[i]['tempSet'] != acs_temp[i]['tempSet']:
            acs[i]['tempSet'] = acs_temp[i]['tempSet']
            topic = "{0}/{1}/{2}/{3}/temp/state".format(
                discovery_prefix, component, node_id, object_id)
            publish(client, topic, int(acs[i]['tempSet']))

        if acs[i]['tempIn'] != acs_temp[i]['tempIn']:
            acs[i]['tempIn'] = acs_temp[i]['tempIn']
            topic = "{0}/{1}/{2}/{3}/cur_temp/state".format(
                discovery_prefix, component, node_id, object_id)
            publish(client, topic, int(acs[i]['tempIn']))

        if acs[i]['fan'] != acs_temp[i]['fan']:
            acs[i]['fan'] = acs_temp[i]['fan']
            topic = "{0}/{1}/{2}/{3}/fan/state".format(
                discovery_prefix, component, node_id, object_id)
            msg = STATES['fan'].get(acs[i]['fan'], 'auto')
            publish(client, topic, msg)


if __name__ == '__main__':
    # setConfig()
    loadConfig()
    client = connect_mqtt()
    subscribe(client)
    client.subscribe("homeassistant/zhonghong/initialize")
    client.loop_start()

    count = 2
    while count > 0:
        initializeClimates(client)
        time.sleep(1)
        count = count - 1

    while True:
        syncACList(client)
        time.sleep(1)
