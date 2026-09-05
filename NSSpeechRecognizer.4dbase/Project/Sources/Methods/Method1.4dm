//%attributes = {}
C_OBJECT:C1216($params)
OB SET:C1220($params; \
"listensInForegroundOnly"; False:C215; \
"blocksOtherRecognizers"; True:C214; \
"displayedCommandsTitle"; "TITLEEEE")

START SPEECH RECOGNIZER("CB"; JSON Stringify:C1217($params))

ARRAY TEXT:C222($commands; 3)
$commands{1}:="Ç±ÇÒÇ…ÇøÇÕ"
$commands{2}:="Ç≥ÇÊÇ§Ç»ÇÁ"
$commands{3}:="Ç®Ç¡Ç∆Ç¡Ç∆"

SET SPEECH COMMANDS($commands)

ARRAY TEXT:C222($commands; 3)
$commands{1}:="Ç∆ÇÒÇ∆ÇÒÇ∆ÇÒ"
$commands{2}:="Ç™ÇÒÇ™ÇÒÇ™ÇÒ"
$commands{3}:="Ç‘ÇÒÇ‘ÇÒÇ‘ÇÒ"

SET SPEECH COMMANDS($commands)

QUIT SPEECH RECOGNIZER