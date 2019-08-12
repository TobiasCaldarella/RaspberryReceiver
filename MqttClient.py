'''
Created on 07.08.2019

@author: tobias
'''
import Configuration
import Coordinator
import paho.mqtt.client as mqtt
from GpioController import PowerState
from threading import Event

class MqttClient(object):
    '''
    classdocs
    '''


    def __init__(self, config: Configuration, coordinator: Coordinator):
        '''
        Constructor
        '''
        self.config = config
        self.logger = config.logger
        client = mqtt.Client()
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_subscribe = self.on_subscribe
        client.enable_logger(self.logger)
        client.username_pw_set(config.mqtt_user, password=config.mqtt_pass)
        client.message_callback_add(self.config.mqtt_base_topic + "/power/set", self.on_power_msg)
        self.client = client
        self.coordinator = coordinator
        coordinator.mqttClient = self
        self.connectEvent = Event()
        
    def connect(self):
        client = self.client
        client.connect(self.config.mqtt_server, self.config.mqtt_port)
        client.subscribe(self.config.mqtt_base_topic + "/power/set")
        client.loop_start()
        
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        
    def publish_power_state(self, state):
        if not isinstance(state, PowerState):
            raise ValueError
         
        if state == PowerState.ON:
            self.client.publish(self.config.mqtt_base_topic + "/power", payload="ON")
        else:
            self.client.publish(self.config.mqtt_base_topic + "/power", payload="OFF")
    
    def waitForSubscription(self):
        self.connectEvent.wait()
    
    def on_power_msg(self, client, userdata, message):
        if self.coordinator is None:
            self.logger.warn("Received Message on power topic but no callback is set")
            return
        pl = message.payload.decode("utf-8")
        if pl == "ON":
            self.coordinator.powerOn()
        elif pl == "OFF":
            self.coordinator.powerOff()
        elif pl == "CHANNEL_UP":
            self.coordinator.channelUp()
        elif pl == "CHANNEL_DOWN":
            self.coordinator.channelDown()
        elif pl == "VOLUME_UP":
            self.coordinator.volumeUp()
        elif pl == "VOLUME_DOWN":
            self.coordinator.volumeDown()
        else:
            self.logger.warn("Received unexpected mqtt message on power topic: '%s'" % (pl))
    
    def on_subscribe(self, client, userdata, mid, granted_qos):
        self.connectEvent.set()
    
    def on_connect(self, client, userdata, flags, rc):
        pass
        
    def on_disconnect(self, client, userdata, rc):
        self.connectEvent.clear()
    
