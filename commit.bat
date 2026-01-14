cd /d "C:\Users\djhui\OneDrive\Github\ha-windows"
git add -A
git commit -m "Fix: 将所有相对导入改为绝对导入"
git push
git tag -d v0.2.0
git tag -a v0.2.1 -m "Release v0.2.1"
git push origin v0.2.1 --force
echo 完成！
