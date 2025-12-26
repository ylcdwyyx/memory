始终保持回答中文,代码注释也中文
如果生成了文件作为工作的结果(不重要的文件不用打开),请使用默认应用打开以方便检查
当前目录如果不是 Git 仓库, git init,代码修改之后存档git
删除文件一定要告知
使用 Chrome DevTools MCP 或写 Playwright 脚本时，接管 CHROME_DEVTOOLS_PORT（未设置为 9222）对应的 Chrome 实例
最常用的mcp服务是Chrome DevTools MCP, 他是一个Model Context Protocol服务器，主要功能是让MCP客户端能够检查和调试浏览器实例
每个项目要有readme,里面要包含项目文件的描述
保持项目结构清晰简洁, 删除调试文件
遇到的调试错误在总结时指出来
python:
    - 用uv管理 Python, uv pip安装依赖
    - 生成或修改的 Python 脚本马上运行测试
    - 所有参数都有非空默认值方便测试
    - 若需要定位默认配置或资源文件，统一通过 Path(__file__).resolve() 向上定位到项
    目根目录，再拼接目标文件，避免依赖执行时的当前工作目录
