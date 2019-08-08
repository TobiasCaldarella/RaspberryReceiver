'''
Created on 07.08.2019

@author: tobias
'''

import Configuration
import logging
import time
import MqttClient
import PowerController

if __name__ == '__main__':
    config = Configuration()
    logger = logging.getLogger()
    logger.setLevel(config.loglevel)
    handler = logging.FileHandler(filename=config.logfile)
    logger.addHandler(handler)
    logger.debug("RaspberryReceiver version %s started." % (config.version))
    config.logger = logger
    
    mqttClient = MqttClient(config)
    mqttClient.connect()
    pwrcnt = PowerController(config)
    time.sleep(10)
    
    