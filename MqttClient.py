'''
Created on 07.08.2019

@author: tobias
'''
import Configuration
import Coordinator
import paho.mqtt.client as mqtt
from GpioController import PowerState
from threading import Event
from paho.mqtt.client import MQTT_ERR_SUCCESS
import sys
import json

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
        try:
            client = self.client
            if client.connect(self.config.mqtt_server, self.config.mqtt_port) is not MQTT_ERR_SUCCESS:
                self.logger.warn("mqtt.connect() failed")
                return False
            for topic in { self.config.mqtt_base_topic + "/power/set", self.config.mqtt_base_topic + "/volume/set", self.config.mqtt_base_topic + "/channel/set"}:
                if client.subscribe(topic)[0] is not MQTT_ERR_SUCCESS:
                    self.logger.warn("mqtt subscription to topic '%s' failed." % topic)
                    return False
            client.loop_start()
            return True
        except:
            self.logger.error("Caught exception in MqttClient.connect(): '%s'" % (sys.exc_info()[0]))
            return False
        
    def disconnect(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
            return True
        except:
            self.logger.error("Caught exception in MqttClient.disconnect(): '%s'" % (sys.exc_info()[0]))
            return False
            
        
    def publish_power_state(self, state):
        if not isinstance(state, PowerState):
            raise ValueError
        try:
            if state == PowerState.ON:
                self.client.publish(self.config.mqtt_base_topic + "/power", payload="ON")
                self.client.publish(self.config.mqtt_base_topic + "/info", payload='{"power": "ON"}')
            else:
                self.client.publish(self.config.mqtt_base_topic + "/power", payload="OFF")
                self.client.publish(self.config.mqtt_base_topic + "/info", payload='{"power": "OFF"}')
            return True
        except:
            self.logger.error("Caught exception in MqttClient.publish_power_state(): '%s'" % (sys.exc_info()[0]))
            return False
            
    
    def pubInfo(self, state, channel, volume, currentSongInfo):
        try:
            self.logger.debug("Publishing status update")
            
            infoDict = {}
            if currentSongInfo is not None:
                infoDict = currentSongInfo
            if volume is not None:
                self.client.publish(self.config.mqtt_base_topic + "/volume", payload=str(volume))
                infoDict['volume'] = volume
            if channel is not None:
                self.client.publish(self.config.mqtt_base_topic + "/channel", payload=str(channel))
                infoDict['channel'] = channel
            if 'title' not in infoDict: 
                if 'name' in infoDict:
                    infoDict['title'] = infoDict['name']
                else:
                    infoDict['title'] = "N/A" 
            
            # state is never none
            if state is True:
                infoDict['state'] = "Playing"
            else:
                infoDict['state'] = "Stopped"
            self.client.publish(self.config.mqtt_base_topic + "/info", payload=str(json.dumps(infoDict))) # output info as json string
        except:
            self.logger.error("Caught exception in MqttClient.pubInfo(): '%s'" % (sys.exc_info()[0]))
    
    def waitForSubscription(self):
        if self.connectEvent.wait(timeout=30.0) is True:
            return True
        self.logger.warn("Timeout waiting for MQTT subscription")
        return False
        
    def on_channel_msg(self, client, userdata, message):
        self.logger.debug("Got channel msg")
        if self.coordinator is None:
            self.logger.warn("Received Message on 'channel' topic but no callback is set")
            return
        try:
            newChannel = int(message.payload.decode("utf-8"))
            self.coordinator.setChannel(newChannel)
        except ValueError:
            self.logger.warn("Invalid data over 'channel' topic received, must be a number")
            
    def on_volume_msg(self, client, userdata, message):
        self.logger.debug("Got volume msg")
        if self.coordinator is None:
            self.logger.warn("Received Message on 'volume' topic but no callback is set")
            return
        try:
            newVolume = int(message.payload.decode("utf-8"))
            if newVolume < 0 or newVolume > 100:
                self.logger.warn("Invalid volume received. Must be: 0 < volume < 100")
            else:
                self.coordinator.setVolume(newVolume)
        except ValueError:
            self.logger.warn("Invalid data over 'volume' topic received, must be a number")
    
    def on_power_msg(self, client, userdata, message):
        if self.coordinator is None:
            self.logger.warn("Received Message on 'power' topic but no callback is set")
            return
        pl = message.payload.decode("utf-8")
        if pl == "ON":
            self.coordinator.powerOn()
        elif pl == "OFF":
            self.coordinator.powerOff()
        else:
            self.logger.warn("Received unexpected mqtt message on 'power' topic: '%s'" % (pl))
    
    def on_subscribe(self, client, userdata, mid, granted_qos):
        self.connectEvent.set()
    
    def on_connect(self, client, userdata, flags, rc):
        pass
        
    def on_disconnect(self, client, userdata, rc):
        self.connectEvent.clear()
    
