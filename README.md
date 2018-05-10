# 4d-plugin-apple-speech-recognizer
4D implementation of [NSSpeechRecognizer](https://developer.apple.com/documentation/appkit/nsspeechrecognizer?language=objc)

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|||

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

### Releases

[1.1](https://github.com/miyako/4d-plugin-apple-speech-recognizer/releases/tag/1.1)

---

## Syntax

```
START SPEECH RECOGNIZER (method;options)
```

Parameter|Type|Description
------------|------------|----
method|TEXT|``callback (TEXT)``
options|TEXT|``JSON``

```
STOP SPEECH RECOGNIZER
QUIT SPEECH RECOGNIZER
```

```
SET SPEECH COMMANDS (commands)
GET SPEECH COMMANDS (commands)
```

Parameter|Type|Description
------------|------------|----
commands|ARRAY TEXT|

## Examples

```
C_OBJECT($params)

  //by default the commands title is the app name i.e. 4D
  //also when the list is empty
  //empty strings (e.g. element 0) are filtered
  //the language respects System Preferences/Voice Recognition and Dictation

OB SET($params;\
"listensInForegroundOnly";False;\
"blocksOtherRecognizers";True;\
"displayedCommandsTitle";"List of Commands")

START SPEECH RECOGNIZER ("CB";JSON Stringify($params))

ARRAY TEXT($commands;3)
$commands{1}:="こんにちは"
$commands{2}:="さようなら"
$commands{3}:="おっとっと"

  //you can change the vocabulary while listening
SET SPEECH COMMANDS ($commands)

ARRAY TEXT($commands;3)
$commands{1}:="とんとんとん"
$commands{2}:="がんがんがん"
$commands{3}:="ぶんぶんぶん"

SET SPEECH COMMANDS ($commands)

  //stop does not end the palette
  //stop SPEECH RECOGNIZER 

  //quit ends the palette
  //QUIT SPEECH RECOGNIZER
```
