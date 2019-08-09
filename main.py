'''
Created on 07.08.2019

@author: tobias
'''

import Configuration
import logging
import time
import MqttClient
import GpioController
import Coordinator
import TuningWheel
from time import sleep

if __name__ == '__main__':
    config = Configuration()
    logger = logging.getLogger()
    logger.setLevel(config.loglevel)
    handler = logging.FileHandler(filename=config.logfile)
    logger.addHandler(handler)
    logger.debug("RaspberryReceiver version %s started." % (config.version))
    config.logger = logger
    
    coordinator = Coordinator(logger)
    if config.gpio_mag_right is not None and config.gpio_mag_left is not None:
        tuning_wheel = TuningWheel(config, coordinator)
    else:
        logger.info("Not initializing TuningWheel since gpio_mag_right and/or gpio_mag_left are not set in configuration")
    
    if config.mqtt_server is not None and config.mqtt_port is not None and config.mqtt_base_topic is not None:
        mqttClient = MqttClient(config, coordinator)
    else:
        logger.info("MqttClient nont initialized since mqtt_server, mqtt_port and/or mqtt_base_topic are not set in configuration")
    
    pwrcnt = GpioController(config, coordinator)

    coordinator.connectWifi()
    coordinator.connectMqtt()
    
    sleep(10)
    
    