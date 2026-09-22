# VMFScript 2.0 Test mit neuer Mechanik
chamber 1024 1024 512

material floor   concrete/concrete_modular_floor001a
material ceiling concrete/concrete_modular_ceiling001a
material wallAB  plastic/plasticwall001b

skyname sky_black_nofog

light 300 500 380 255 255 255 180
spawn 512 300 64
gun   560 300 64

button at 420 700 0 target btn_01
door   at 512 990 0 target door_01
wire   btn_01.OnPressed -> door_01.Open

bumper at 200 600 0 400 800 256
noportal at 700 200 0 900 400 256
