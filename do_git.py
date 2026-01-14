import subprocess
import os

os.chdir(r"C:\Users\djhui\OneDrive\Github\ha-windows")

print("当前目录:", os.getcwd())

# 添加所有修改
print("\n1. 添加修改...")
r = subprocess.run("git add -A", shell=True, capture_output=True, text=True)
print(r.stdout if r.stdout else r.stderr)

# 提交
print("\n2. 提交...")
r = subprocess.run('git commit -m "Fix: 将所有相对导入改为绝对导入"', shell=True, capture_output=True, text=True)
print(r.stdout if r.stdout else r.stderr)

# 推送
print("\n3. 推送...")
r = subprocess.run("git push", shell=True, capture_output=True, text=True)
print(r.stdout if r.stdout else r.stderr)

# 删除旧 tag
print("\n4. 删除旧 tag...")
r = subprocess.run("git tag -d v0.2.0", shell=True, capture_output=True, text=True, stderr=subprocess.DEVNULL)

# 创建新 tag
print("\n5. 创建新 tag v0.2.1...")
r = subprocess.run('git tag -a v0.2.1 -m "Release v0.2.1"', shell=True, capture_output=True, text=True)
print(r.stdout if r.stdout else r.stderr)

# 推送 tag
print("\n6. 推送 tag...")
r = subprocess.run("git push origin v0.2.1 --force", shell=True, capture_output=True, text=True)
print(r.stdout if r.stdout else r.stderr)

print("\n✅ 完成！")
