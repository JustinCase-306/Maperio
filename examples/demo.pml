# Demo: Eine kleine durchspielbare Portal-Kammer
# Kompilieren:  python portalmap.py demo.pml --compile

chamber 1024 1024 512

material floor   concrete/concrete_modular_floor001a
material ceiling concrete/concrete_modular_ceiling001a
material wallAB  plastic/plasticwall001b
material wallCD  plastic/plasticwall001a

light 300 500 380 255 255 255 200
light 720 500 380 255 235 210 220

spawn 512 512 64
gun   560 512 64

# Mechanik: Bodenschalter oeffnet die Testkammer-Tuer
button at 420 700 0 target door_btn
door   at 512 990 0 target door_01
wire   door_btn.OnPressed -> door_01.Open

# Etwas Deko
prop models/props/sign_frame01/sign_frame01.mdl at 160 120 300 skin 0