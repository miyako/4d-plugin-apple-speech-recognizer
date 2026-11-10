#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <map>
#include <set>
#include <string>

namespace SR {
extern C_TEXT LISTENER_METHOD;
extern std::vector<CUTF16String> RECOGNIZED_COMMANDS;
}
void listenerLoopExecuteMethod();
void PluginMain(PA_long32, PA_PluginParameters) {}

static bool allocatedEmpty;
static bool projectMethod;
static int resultKind;
static std::set<PA_Unichar *> strings;
static std::map<PA_Handle, size_t> handles;
static CUTF16String expected;
static CUTF16String methodName((const PA_Unichar *)u"callback_\u65e5\U0001f399");

static CUTF16String content(const PA_Unistring &string)
{
    if (!string.fString) {
        assert(string.fLength == 0);
        return CUTF16String();
    }
    PA_Unichar *buffer = string.fString;
    assert(strings.count(buffer));
    assert(string.fString[string.fLength] == 0);
    return CUTF16String(string.fString, string.fLength);
}

static PA_Unistring create(const PA_Unichar *text)
{
    PA_Unistring string = {};
    size_t units = 0;
    while (text[units]) ++units;
    if (units || allocatedEmpty) {
        string.fString = (PA_Unichar *)malloc((units + 1) * sizeof(PA_Unichar));
        memcpy(string.fString, text, (units + 1) * sizeof(PA_Unichar));
        PA_Unichar *buffer = string.fString;
        assert(strings.insert(buffer).second);
    }
    string.fLength = units;
    return string;
}

static void dispose(PA_Unistring &string)
{
    if (string.fString) {
        PA_Unichar *buffer = string.fString;
        assert(strings.erase(buffer) == 1 && "double dispose or borrowed string");
        free(string.fString);
    }
    string = {};
}

static void clear(PA_Variable &variable)
{
    if (variable.fType == eVK_Unistring) {
        dispose(variable.uValue.fString);
    } else if (variable.fType == eVK_ArrayUnicode) {
        auto &array = variable.uValue.fArray;
        auto data = (PA_Unistring *)*array.fData;
        for (int i = 0; i <= array.fNbElements; ++i) dispose(data[i]);
        PA_DisposeHandle(array.fData);
    } else {
        assert(variable.fType == eVK_Undefined || variable.fType == eVK_Picture);
    }
    variable = {};
    variable.fType = eVK_Undefined;
}

static void setResult(PA_Variable &result)
{
    result = {};
    result.fType = eVK_Undefined;
    if (resultKind) {
        result.fType = eVK_Unistring;
        result.uValue.fString = create(resultKind == 2 ? expected.c_str()
            : (const PA_Unichar *)u"unused_\u65e5\U0001f399");
    }
}

static void engine(short selector, EngineBlock *eb)
{
    switch (selector) {
    case EX_CREATE_UNISTRING:
        eb->fUniString1 = create((PA_Unichar *)eb->fHandle);
        break;
    case EX_DISPOSE_UNISTRING:
        dispose(eb->fUniString1);
        break;
    case EX_SET_UNISTRING: {
        CUTF16String copy((PA_Unichar *)eb->fHandle);
        dispose(eb->fUniString1);
        eb->fUniString1 = create(copy.c_str());
        break;
    }
    case EX_CLEAR_VARIABLE:
        clear(*(PA_Variable *)eb->fPtr1);
        break;
    case EX_GET_METHOD_ID:
        eb->fParam1 = projectMethod ? 42 : 0;
        break;
    case EX_CALL_BY_PROCID: {
        assert(eb->fParam1 == 42 && eb->fParam2 == 1);
        auto parameters = (PA_Variable *)*eb->fHandle;
        assert(content(parameters[1].uValue.fString) == expected);
        setResult(parameters[0]);
        break;
    }
    case EX_EXECUTE_COMMAND_BY_ID: {
        auto parameters = (PA_Variable **)eb->fPtr1;
        if (eb->fParam1 == 1007) {
            assert(eb->fParam2 == 2);
            assert(content(parameters[0]->uValue.fString) == methodName);
            assert(content(parameters[1]->uValue.fString) == expected);
        } else if (eb->fParam1 == 678) {
            assert(content(parameters[0]->uValue.fString) == expected);
        } else {
            assert(eb->fParam1 == 1002);
            assert(content(parameters[1]->uValue.fString) == expected);
        }
        setResult(*(PA_Variable *)eb->fPtr2);
        break;
    }
    case EX_HANDLE_MANAGER: {
        PA_Handle handle = eb->fParam1 == 1 ? nullptr : eb->fHandle;
        switch (eb->fParam1) {
        case 1:
            handle = (PA_Handle)malloc(sizeof(char *));
            *handle = (char *)calloc(1, eb->fParam2);
            handles[handle] = eb->fParam2;
            eb->fHandle = handle;
            break;
        case 2:
            assert(handles.erase(handle) == 1);
            free(*handle);
            free(handle);
            break;
        case 3:
            assert(handles.count(handle));
            *handle = (char *)realloc(*handle, eb->fParam2);
            handles[handle] = eb->fParam2;
            break;
        case 4:
            eb->fParam2 = handles.at(handle);
            break;
        case 5:
            assert(handles.count(handle));
            eb->fParam3 = (sLONG_PTR)*handle;
            break;
        case 6:
            break;
        default:
            assert(false);
        }
        eb->fError = 0;
        break;
    }
    case EX_CONVERT_CHARSET_TO_CHARSET: {
        assert(eb->fParam2 == eVTC_UTF_8 && eb->fParam4 == eVTC_UTF_16);
        CFStringRef text = CFStringCreateWithBytes(
            kCFAllocatorDefault, (const UInt8 *)eb->fPtr1, eb->fParam1,
            kCFStringEncodingUTF8, false);
        assert(text);
        CFIndex units = CFStringGetLength(text);
        assert(eb->fParam3 >= units * (CFIndex)sizeof(PA_Unichar));
        CFStringGetCharacters(text, CFRangeMake(0, units), (UniChar *)eb->fPtr2);
        // The SDK returns bytes, excludes termination, and receives byte capacity.
        eb->fParam3 = units * sizeof(PA_Unichar);
        eb->fError = 0;
        CFRelease(text);
        break;
    }
    case EX_CREATE_PICTURE:
        eb->fPicture = nullptr; // Empty pictures have no payload in this string-only shim.
        eb->fError = 0;
        break;
    case EX_DISPOSE_PICTURE:
    case EX_DUPLICATE_PICTURE:
        assert(!eb->fPicture);
        break;
    default:
        assert(false && "unexpected engine selector");
    }
}

static void arrayCase()
{
    PA_Variable variable = PA_CreateVariable(eVK_ArrayUnicode);
    BytePtr pointer = (BytePtr)&variable;
    PackagePtr parameters = &pointer;
    ARRAY_TEXT values;
    values.appendUTF16String((const PA_Unichar *)u"");
    values.appendUTF16String((const PA_Unichar *)u"hello");
    values.appendUTF16String((const PA_Unichar *)u"\u65e5\U0001f399");
    for (int repeat = 0; repeat < 20; ++repeat) {
        values.toParamAtIndex(parameters, 1);
        for (int churn = 0; churn < 100; ++churn) {
            PA_Unistring temporary = create((const PA_Unichar *)u"allocator churn");
            dispose(temporary);
        }
        for (int i = 0; i < 3; ++i) {
            CUTF16String text;
            values.copyUTF16StringAtIndex(&text, i);
            assert(content(PA_GetStringInArray(variable, i)) == text);
        }
        ARRAY_TEXT copy;
        copy.fromParamAtIndex(parameters, 1);
        PA_ResizeArray(&variable, 0);
        CUTF16String text;
        copy.copyUTF16StringAtIndex(&text, 2);
        assert(text == CUTF16String((const PA_Unichar *)u"\u65e5\U0001f399"));
    }
    PA_Unistring rejected = create((const PA_Unichar *)u"caller-owned");
    PA_Variable wrong = {};
    PA_SetStringInArray(wrong, 0, &rejected);
    PA_SetStringInArray(variable, -1, &rejected);
    PA_SetStringInArray(variable, 1, &rejected);
    PA_Variable missing = variable;
    missing.uValue.fArray.fData = nullptr;
    PA_SetStringInArray(missing, 0, &rejected);
    assert(content(rejected) == CUTF16String((const PA_Unichar *)u"caller-owned"));
    dispose(rejected);
    PA_ClearVariable(&variable);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    allocatedEmpty = std::string(argv[1]) == "allocated";
    gCall4D = engine;
    std::string test = argv[2];
    if (test == "array") {
        arrayCase();
    } else if (test == "path") {
        C_PICTURE picture;
        CUTF8String path((const uint8_t *)u8"/tmp/\u65e5\U0001f399.png");
        expected = (const PA_Unichar *)u"/tmp/\u65e5\U0001f399.png";
        picture.fromFileAtPath(&path);
    } else if (test == "copy") {
        CPicture picture;
        for (auto format : {".png", ".jpg", ".tif", u8".\u65e5\U0001f399", ""}) {
            C_TEXT text;
            text.setUTF8String((const uint8_t *)format, strlen(format));
            expected = text.getUTF16StringPtr();
            PA_DisposePicture(picture.createCopy(format));
        }
    } else {
        projectMethod = test == "method";
        SR::LISTENER_METHOD.setUTF16String(methodName.c_str(), methodName.size());
        for (auto text : {u"hello", u"\u65e5\U0001f399", u""}) {
            for (int result : {0, 1, 2}) {
                resultKind = result;
                expected = (const PA_Unichar *)text;
                SR::RECOGNIZED_COMMANDS.push_back(expected);
                listenerLoopExecuteMethod();
                assert(SR::RECOGNIZED_COMMANDS.empty());
                assert(strings.empty() && "callback argument or unused result leaked");
            }
        }
    }
    assert(strings.empty() && "owned string allocation leaked");
    assert(handles.empty());
}
