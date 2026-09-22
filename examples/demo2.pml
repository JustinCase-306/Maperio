chamber 1024 1024 512
material floor concrete/concrete_modular_floor001a
material ceiling concrete/concrete_modular_ceiling001a
light 300 500 380 255 255 255 200
spawn 512 512 64
gun 560 512 64
button at 420 700 0 target door_btn
door at 512 990 0 target door_01
wire door_btn.OnPressed -> door_01.Open
