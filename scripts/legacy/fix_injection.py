"""Fix prompt injection patterns."""
with open('app/generate/prompt_injection_detector.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the _ROLE_PLAYING list and add patterns
old = 'r"你是一个.*?[，,.]",\n        r"act as",\n        r"扮演.*?[的].*?[角色]",'

new = 'r"你是一个.*?[，,.]",\n        r"你是一个.*?不受",\n        r"不受限制",\n        r"不受约束",\n        r"回答任何问题",\n        r"没有限制",\n        r"没有约束",\n        r"不需要.*?限制",\n        r"不需要.*?约束",\n        r"扮演.*?[的]",\n        r"扮演.*?AI",\n        r"扮演.*?不受",\n        r"扮演.*?任何",\n        r"act as",\n        r"扮演.*?[的].*?[角色]",'

if old in content:
    content = content.replace(old, new)
    with open('app/generate/prompt_injection_detector.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('patched')
else:
    print('old not found')
    # Show what's there
    idx = content.find('你是一个')
    if idx >= 0:
        print(content[idx:idx+300])