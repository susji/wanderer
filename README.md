# wanderer

We implement a simple control software and data plotter for a device called the
Wanderer. It was also known by its Finnish translation Kulkuri. The device is a
battery-operated and portable sensor device manufactured around 1991 by
Elektrobit/Extrabit. The only unit I've seen measures ambient temperature and
vibration as a function of time. The device came with a disk containing a
control program meant for Windows 2 and 3. The interesting parts of the original
software are reimplemented here.

I haven't seen any technical documentation for this device and I'm not sure if
it even exists at this point. I reverse engineered the serial protocol. There
are probably some mistakes and misinterpretations.

So far I've only gotten the device to work with Windows 10 and using a
motherboard provided RS232 serial port. No luck with a few different USB-RS232
adapters on Windows or Linux...
