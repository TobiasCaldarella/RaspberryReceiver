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
        client.message_callback_add(self.config.mqtt_base_topic + "/volume/set", self.on_volume_msg)
        client.message_callback_add(self.config.mqtt_base_topic + "/channel/set", self.on_channel_msg)
        self.client = client
        self.coordinator = coordinator
        coordinator.mqttClient = self
        self.connectEvent = Event()
        
    def connect(self):
        client = self.client
        client.connect(self.config.mqtt_server, self.config.mqtt_port)
        client.subscribe(self.config.mqtt_base_topic + "/power/set")
        client.subscribe(self.config.mqtt_base_topic + "/volume/set")
        client.subscribe(self.config.mqtt_base_topic + "/channel/set")
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
    
    def pubInfo(self, state, channel+1, volume, currentSongInfo):
        self.logger.debug("Publishing status update")
        #todo: decouple!
        self.client.publish(self.config.mqtt_base_topic + "/volume", payload=volume)
        self.client.publish(self.config.mqtt_base_topic + "/channel", payload=channel)
        self.client.publish(self.config.mqtt_base_topic + "/info", payload=currentSongInfo) # todo: filter
    
    def waitForSubscription(self):
        self.connectEvent.wait()
        
    def on_channel_msg(self, client, userdata, message):
        self.logger.debug("Got channel msg")
        if self.coordinator is None:
            self.logger.warn("Received Message on 'channel' topic but no callback is set")
            return
        newChannel = message.payload
        if isinstance(newChannel, int):
            self.coordinator.setChannel(newChannel)
        else:
            self.logger.warn("Invalid data over 'channel' topic received")
            
    def on_volume_msg(self, client, userdata, message):
        self.logger.debug("Got volume msg")
        if self.coordinator is None:
            self.logger.warn("Received Message on 'volume' topic but no callback is set")
            return
        newVolume = message.payload
        if isinstance(newVolume, int):
            self.coordinator.setVolume(newVolume)
        else:
            self.logger.warn("Invalid data over 'volume' topic received")
    
    def on_power_msg(self, client, userdata, message):
        if self.coordinator is None:
            self.logger.warn("Received Message on 'power' topic but no callback is set")
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
            self.logger.warn("Received unexpected mqtt message on 'power' topic: '%s'" % (pl))
    
    def on_subscribe(self, client, userdata, mid, granted_qos):
        self.connectEvent.set()
    
    def on_connect(self, client, userdata, flags, rc):
        pass
        
    def on_disconnect(self, client, userdata, rc):
        self.connectEvent.clear()
    
