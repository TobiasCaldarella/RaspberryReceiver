'''
Created on 08.11.2020

@author: tobias
'''
import threading
import subprocess
import os

class Upmp(object):
    '''
    classdocs
    '''


    def __init__(self, config, coordinator):
        '''
        Constructor
        '''
        self.upmp_config = config.upmp_config_file
        self.workerThread = None
        self.logger = coordinator.logger
        self.coordinator = coordinator
        coordinator.upmp = self
        self.upmp_process = None
        self.stop_timer = None
        
    def enable(self):
        self.logger.info("Enabling upmp")
        self.workerThread = threading.Thread(target = self._workerThreadFct, name = "UpmpWorker")
        self.workerThread.start()
        
    def disable(self):
        self.logger.info("Disabling upmp")
        if self.stop_timer is not None:
            self.stop_timer.cancel()
        if self.workerThread: 
            if self.upmp_process is not None:
                self.logger.info("terminating upmpdcli process")
                self.upmp_process.terminate()
                os.system("killall upmpdcli")
            if self.workerThread.is_alive():
                self.workerThread.join(2.0)
                if self.workerThread.is_alive():
                    self.logger.error("Upmp: Worker thread did not end!")
                else:
                    self.workerThread = None
        
    def _workerThreadFct(self):
        self.logger.info("Upmp: worker thread started")
        self.upmp_process = subprocess.Popen(["upmpdcli -c " + self.upmp_config + " 2>&1"], shell=True, stdout=subprocess.PIPE) 
        while self.upmp_process.poll() is None:
            output = (self.upmp_process.stdout.readline()).decode('utf-8').rstrip()
            self.logger.info("upmpdcli: '%s'" % output)
            if self.stop_timer is not None:
                self.stop_timer.cancel()
            if output == "___UPNP playback about to start":
                self.coordinator.upnpPlaybackStartCallback()
            elif output == "___UPNP stop":
                self.stop_timer = threading.Timer(interval=3.0, function=self.coordinator.upnpStopCallback)
                self.stop_timer.start()
        rc = self.upmp_process.poll()
        self.logger.info("upmpdcli exited with rc %d" % rc)
        self.coordinator.upnpStopCallback()
        self.upmp_process = None
        
        