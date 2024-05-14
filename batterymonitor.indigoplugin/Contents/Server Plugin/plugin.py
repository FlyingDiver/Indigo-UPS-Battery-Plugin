#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2011, Benjamin Schollnick. All rights reserved.
# http://www.schollnick.net/Wordpress
#
# Copyright (c) 2024, Joe Keenan
#
################################################################################

import subprocess
import time
import logging

CURRENT_DEVICE_VERSION = 4

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)
        self.logLevel = int(pluginPrefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        self.plugin_file_handler.setLevel(self.logLevel)
        self.pluginPrefs = pluginPrefs

        self.monitors = []
        self.verify_preference("Timing", 5)
        self.verify_preference("PowerFailureTiming", 1)

    def startup(self):
        self.logger.debug("startup called")

    def shutdown(self):
        self.logger.debug("shutdown called")

    def verify_preference(self, preference_key, default_value):
        if preference_key in self.pluginPrefs:
            return
        else:
            self.pluginPrefs[preference_key] = default_value

    @staticmethod
    def verify_device_properties(dev, property_name, boolean=False, default_value=""):
        newProps = dev.pluginProps  # dev.globalProps[plugin_id]
        if property_name in newProps:
            return
        else:
            if boolean:
                newProps[property_name] = True
            else:
                newProps[property_name] = default_value

            dev.replacePluginPropsOnServer(newProps)

    @staticmethod
    def update_device_property(dev, property_name, new_value):
        newProps = dev.pluginProps
        newProps.update({property_name: new_value})
        dev.replacePluginPropsOnServer(newProps)
        return None

    ########################################

    def deviceStartComm(self, dev):
        self.verify_device_properties(dev, "Status", boolean=False, default_value="Unknown")
        self.verify_device_properties(dev, "device_version", boolean=False, default_value="000")
        self.verify_device_properties(dev, "Model", boolean=False, default_value="")
        self.verify_device_properties(dev, "ACPower", boolean=True)
        self.verify_device_properties(dev, "PowerSource", boolean=False, default_value="")

        device_version = int(dev.pluginProps["device_version"])
        if device_version != CURRENT_DEVICE_VERSION:
            self.update_device_property(dev, "device_version", new_value=current_device_version)

        if dev.deviceTypeId == "BatteryMonitor":
            if len(self.monitors) >= 1:
                self.errorLog("Only One Battery & UPS Monitor device can be used.")
            else:
                self.monitors.append(dev.id)

        dev.stateListOrDisplayStateIdChanged()

    def deviceStopComm(self, dev):
        if dev.deviceTypeId == "BatteryMonitor":
            self.monitors.remove(dev.id)

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.logger.threaddebug(f"closedPrefsConfigUi: valuesDict = {valuesDict}")
            self.logLevel = int(self.pluginPrefs.get("logLevel", logging.INFO))
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(f"logLevel = {self.logLevel}")

    def runConcurrentThread(self):
        try:
            while True:

                if self.monitors == {}:
                    self.logger.info("No Battery & UPS Monitor device defined.")
                    self.sleep(int(self.pluginPrefs["Timing"]) * 60)
                    continue
                else:
                    battery_monitor_device = indigo.devices[self.monitors[0]]

                # get battery status

                proc = subprocess.Popen(['pmset', '-g', 'batt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = proc.communicate()
                out = out.decode('utf8').split("\n")
                self.logger.debug(f"get_battery_status() = {out}")

                if len(out) == 2:       # no UPS connected
                    battery_monitor_device.updateStateOnServer("Status", "No UPS")
                    self.sleep(int(self.pluginPrefs["Timing"]) * 60)
                    continue

                power_status = out[0].split("'")[1]
                battery_monitor_device.updateStateOnServer("Status", power_status)

                data = out[1].split("\t")
                ups_model = data[0]
                data = data[1].split(";")
                percentage = data[0][0:-1]  # data[1][0:percent_locale]
                charging = data[1].find("discharging") == -1
                if not charging:
                    ctime = data[2][0:data[2].find(":") + 3].strip()
                    c_hours = data[2][0:ctime.find(":") + 1]
                    c_min = data[2][ctime.find(":") + 2:ctime.find(":") + 4]
                    time_remaining = int(c_hours) * 60 + int(c_min)
                else:
                    ctime = 0
                    c_hours = 0
                    c_min = 0
                    time_remaining = 0

                if battery_monitor_device.states["Model"] != ups_model:
                    battery_monitor_device.updateStateOnServer("Model", ups_model)

                if battery_monitor_device.states["ACPower"] != power_status:
                    battery_monitor_device.updateStateOnServer("ACPower", power_status)

                if battery_monitor_device.states["Charging"] != charging:
                    battery_monitor_device.updateStateOnServer("Charging", charging)

                if battery_monitor_device.states["BatteryLevel"] != percentage:
                    battery_monitor_device.updateStateOnServer("BatteryLevel", percentage)

                if battery_monitor_device.states["BatteryTimeRemaining"] != time_remaining:
                    battery_monitor_device.updateStateOnServer("BatteryTimeRemaining", time_remaining)

                if battery_monitor_device.states["PowerSource"] != power_status:
                    battery_monitor_device.updateStateOnServer("PowerSource", power_status)

                battery_monitor_device.updateStateOnServer("TimeDateStamp", time.ctime())

                if charging:
                    self.sleep(int(self.pluginPrefs["Timing"]) * 60)
                else:
                    self.sleep(int(self.pluginPrefs["PowerFailureTiming"]) * 60)

        except self.StopThread:
            self.logger.debug("Stopping Plugin")
