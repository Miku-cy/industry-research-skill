# 贡献指南

感谢您对 ChronoVisor 的兴趣！欢迎贡献代码、报告问题或提出改进建议。

---

## 如何贡献

### 1. Fork 仓库

点击 GitHub 页面右上角的 **Fork** 按钮，创建您自己的仓库副本。

### 2. 克隆仓库

```bash
git clone https://github.com/你的用户名/industry-research-skill.git
cd industry-research-skill
```

### 3. 创建分支

```bash
git checkout -b feature/你的功能名称
```

### 4. 进行修改

- 编写代码
- 添加测试
- 更新文档

### 5. 提交更改

```bash
git add .
git commit -m "feat: 添加新功能"
```

### 6. 推送到 GitHub

```bash
git push origin feature/你的功能名称
```

### 7. 创建 Pull Request

在 GitHub 上创建 PR，描述您的更改内容和动机。

---

## 代码规范

### Python 代码

- 使用 **PEP 8** 代码风格
- 类名使用 `CamelCase`
- 函数和变量使用 `snake_case`
- 所有公共方法需要文档字符串

### 提交信息格式

```
<type>: <subject>

<body>
```

**Type 类型：**
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 维护任务

---

## 测试要求

- 所有新功能必须包含测试
- 确保所有测试通过：
  ```bash
  python tests/test_timeline.py
  ```

---

## 问题反馈

### Bug 报告

请包含：
- 复现步骤
- 预期行为
- 实际行为
- 环境信息（Python 版本等）

### 功能建议

请描述：
- 问题的背景
- 您的解决方案
- 可能的替代方案

---

## 许可证

通过贡献代码，您同意您的贡献将按照 MIT 许可证授权。

---

## 联系方式

- GitHub Issues: https://github.com/Miku-cy/industry-research-skill/issues
- GitHub Profile: https://github.com/Miku-cy

感谢您的贡献！🎉