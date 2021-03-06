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
from Configuration import _RadioState
import threading

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
        client.message_callback_add(self.config.mqtt_base_topic + "/brightness/set", self.on_brightness_msg)
        client.message_callback_add(self.config.mqtt_base_topic + "/commands", self.on_command_msg)
        self.client = client
        self.coordinator = coordinator
        coordinator.mqttClient = self
        self.connectEvent = Event()
        self.retry_timer = None
        
    def connect(self): 
        client = self.client
        client.loop_start()
        try:
            if client.connect(self.config.mqtt_server, self.config.mqtt_port) is not MQTT_ERR_SUCCESS:
                self.logger.warn("mqtt.connect() failed")
                return False
            return True
        except:
            self.logger.error("Caught exception in MqttClient.connect(): '%s'" % (sys.exc_info()[0]))
            return False
        
    def reconnect(self):
        self.logger.info("mqtt reconnecting...")        
        try:
            if self.client.reconnect() is MQTT_ERR_SUCCESS:
                return True
            else:
                self.logger.warn("mqtt.reconnect() failed")
        except:
            self.logger.error("Caught exception in MqttClient.reconnect(): '%s'" % (sys.exc_info()[0]))
        self.logger.warn("will retry in %i seconds" % self.config.mqtt_reconnect_period_s)
        if self.retry_timer is not None:
            self.retry_timer.cancel()
        self.retry_timer = threading.Timer(self.config.mqtt_reconnect_period_s, self.reconnect)
        self.retry_timer.start()
        
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
            
    
    def pubInfo(self, currentState, channel, volume, currentSongInfo, numChannelsInPlaylist, brightness, poweredOn, bluetooth):
        try:
            self.logger.info("Publishing status update to mqtt")
            
            infoDict = {}
            if currentSongInfo is not None:
                infoDict = currentSongInfo
                
            self.client.publish(self.config.mqtt_base_topic + "/volume", payload=str(volume))
            infoDict['volume'] = volume
            self.client.publish(self.config.mqtt_base_topic + "/channel", payload=str(channel))
            infoDict['channel'] = channel
            infoDict['numChannelsInPlaylist'] = numChannelsInPlaylist 
            if 'name' not in infoDict:
                infoDict['name'] = "N/A"
            if 'title' in infoDict:
                title = infoDict['title']
                if title.find('|lang=') >= 0:
                    infoDict['title'] = title.split('|lang=')[0]
            else:
                infoDict['title'] = "N/A" 
            
            infoDict['brightness'] = brightness
            if poweredOn == True:
                infoDict['power'] = "ON"
            else:
                infoDict['power'] = "OFF"
            
            infoDict['state'] = currentState
            if bluetooth is True:
                infoDict['bluetooth'] = "ON"
            else:
                infoDict['bluetooth'] = "OFF"                
            
            infoDict['notify'] = 0 # always0 for now, required to workaround bug in openHAB
            self.client.publish(self.config.mqtt_base_topic + "/info", payload=str(json.dumps(infoDict))) # output info as json string
        except Exception as ex:
            self.logger.error("Caught exception in MqttClient.pubInfo(): '%s'" % (ex))
    
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
            self.coordinator.setChannel(channel = newChannel-1, relative = False, setIfPowerOff = True)  # channel starts at 0
        except ValueError:
            self.logger.warn("Invalid data over 'channel' topic received, must be a number")
        except UnicodeDecodeError:
            self.logger.warn("Invalid data over 'channel' topic received, must be a number in an utf-8 string")
            
    def on_volume_msg(self, client, userdata, message):
        self.logger.debug("Got volume msg")
        if self.coordinator is None:
            self.logger.warn("Received Message on 'volume' topic but no callback is set")
            return
        try:
            newVolume = message.payload.decode("utf-8")
            if newVolume == "up" or newVolume == "UP":
                self.coordinator.volumeUp()
            elif newVolume == "down" or newVolume == "DOWN":
                self.coordinator.volumeDown()
            else:
                newVolumeAsInt = int(newVolume)
                if newVolumeAsInt < 0 or newVolumeAsInt > 100:
                    self.logger.warn("Invalid volume received. Must be: 0 < volume < 100")
                else:
                    self.coordinator.setVolume(vol=newVolumeAsInt, waitForPoti=True)
        except ValueError:
            self.logger.warn("Invalid data over 'volume' topic received, must be a number")
        except UnicodeDecodeError:
            self.logger.warn("Invalid data over 'volume' topic received, must be a number in an utf-8 string")
    
    def on_power_msg(self, client, userdata, message):
        if self.coordinator is None:
            self.logger.warn("Received Message on 'power' topic but no callback is set")
            return
        try:
            pl = message.payload.decode("utf-8")
            if pl == "ON":
                self.coordinator.powerOn()
            elif pl == "OFF":
                self.coordinator.powerOff()
            else:
                self.logger.warn("Received unexpected mqtt message on 'power' topic: '%s'" % (pl))
        except UnicodeDecodeError:
            self.logger.warn("Invalid data over 'power' topic received, must be a utf-8 string")
    
    def on_brightness_msg(self, client, userdata, message):
        if self.coordinator is None:
            self.logger.warn("Received Message on 'brightness' topic but no callback is set")
            return
        try:
            brightness = int(message.payload.decode("utf-8"))
            if brightness < 0 or brightness > 100:
                self.logger.warn("Invalid brightness received, must be between 0 and 100")
                return
            self.coordinator.setBrightness(brightness)
        except ValueError:
            self.logger.warn("Invalid data over 'brightness' topic received, must be a number in an utf-8 string")
        except UnicodeDecodeError:
            self.logger.warn("Invalid data over 'brightness' topic received, must be a number in an utf-8 string")
            
    def on_command_msg(self, client, userdata, message):
        try:
            payload = message.payload.decode("utf-8")
            self.logger.debug("Received payload on commands topic: '%s'", payload)
            commands = json.loads(payload);
            self.logger.info("Received commands: %s", commands)
            self.coordinator.setSkipMqttUpdates(skip=True)
            if 'channel' in commands:
                self.coordinator.setChannel(channel = int(commands['channel'])-1, relative = False, setIfPowerOff = True)  # channel starts at 0
            if 'volume' in commands:
                if commands['volume'] == "up" or commands['volume'] == "UP":
                    self.coordinator.volumeUp()
                elif commands['volume'] == "down" or commands['volume'] == "DOWN":
                    self.coordinator.volumeDown()
                else:
                    self.coordinator.setVolume(vol=int(commands['volume']), waitForPoti=True)

            if 'speak' in commands:
                if commands['speak'].find('|lang=') >= 0:
                    langAndText = commands['speak'].split('|lang=')
                    lang = langAndText[1]
                    text = langAndText[0]
                else:
                    lang = 'de-de'
                    text = commands['speak']
                self.coordinator.speak(text, lang)
            if 'power' in commands:
                if commands['power'] == 'ON':
                    self.coordinator.powerOn() # powerOn will call setSkipMqttUpdates(False), so must be last command
                if commands['power'] == 'OFF':
                    self.coordinator.powerOff()
        except ValueError:
            self.logger.warn("Invalid data over 'commands' topic received, must be a utf-8 json string with commands")
        except UnicodeDecodeError:
            self.logger.warn("Invalid data over 'commands' topic received, must be a utf-8 json string")
        # re-enable updates (will also send an update immediately after all enqueued commands were executed)
        self.coordinator.setSkipMqttUpdates(False)
        
    def on_subscribe(self, client, userdata, mid, granted_qos):
        pass
    
    def on_connect(self, client, userdata, flags, rc):
        self.logger.info("MQTT connecton established")
        for topic in { self.config.mqtt_base_topic + "/power/set", self.config.mqtt_base_topic + "/volume/set", self.config.mqtt_base_topic + "/channel/set", self.config.mqtt_base_topic + "/notify/set", self.config.mqtt_base_topic + "/brightness/set", self.config.mqtt_base_topic + "/commands"}:
            if client.subscribe(topic)[0] is not MQTT_ERR_SUCCESS:
                self.logger.warn("mqtt subscription to topic '%s' failed." % topic)
        self.connectEvent.set()
        
    def on_disconnect(self, client, userdata, rc):
        self.logger.warn("MQTT connection lost!")
        self.connectEvent.clear()
