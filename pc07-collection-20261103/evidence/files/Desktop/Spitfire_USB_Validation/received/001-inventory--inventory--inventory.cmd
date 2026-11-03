@echo off
ipconfig /all > C:\SPF_USB_VALIDATION\ipconfig.txt
route print > C:\SPF_USB_VALIDATION\routes.txt
tasklist > C:\SPF_USB_VALIDATION\tasks.txt
sc query npf > C:\SPF_USB_VALIDATION\npf.txt
dir C:\WINDOWS\system32\wpcap.dll C:\WINDOWS\system32\Packet.dll C:\WINDOWS\system32\drivers\npf.sys > C:\SPF_USB_VALIDATION\driverfiles.txt 2>&1
"C:\SPF_ORIGINAL_CAPTURE_20261101\guest_driver.exe" inventory "C:\SPF_USB_VALIDATION\initial"
