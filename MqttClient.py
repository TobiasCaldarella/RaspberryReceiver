'''
Created on 07.08.2019

@author: tobias
'''
from RaspberryReceiver import Configuration
import paho.mqtt.client as mqtt
from RaspberryReceiver.PowerController import PowerState

class MqttClient(object):
    '''
    classdocs
    '''


    def __init__(self, config : Configuration):
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
        client.message_callback_add(self.config.mqtt_base_topic + "/power", self.on_power_msg)
        #client.on_message = on_message
        self.client = client
        self.setPower = None
        
    def connect(self):
        client = self.client
        client.connect(self.config.mqtt_server, self.config.mqtt_port)
        client.subscribe(self.config.mqtt_base_topic + "/power")
        client.loop_start()
        
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        
    def publish_power_state(self, state):
        if not isinstance(state, PowerState):
            raise ValueError
         
        if state == PowerState.OFF:
            self.client.publish(self.config.mqtt_base_topic + "/power", payload="ON")
        else:
            self.client.publish("power", payload="OFF")
    
    def on_power_msg(self, client, userdata, message):
        if self.setPower is None:
            self.logger.warn("Received Message on power topic but no callback is set")
            return
        if message.payload == "ON":
            self.setPower(PowerState.ON)
        elif message.payload == "OFF":
            self.setPower(PowerState.OFF)
        else:
            self.logger.warn("Received unexpected mqtt message on power topic: '%s'" % (message.payload))
    
    def on_subscribe(self, client, userdata, mid, granted_qos):
        pass    
    
    def on_connect(self, client, userdata, flags, rc):
        pass
        
    def on_disconnect(self, client, userdata, rc):
        pass
    