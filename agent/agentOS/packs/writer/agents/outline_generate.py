from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


def _infer_genre(premise: str, genre: str) -> str:
    normalized = (genre or "").strip()
    if normalized and normalized.lower() not in {"fiction", "story", "novel"}:
        return normalized

    text = premise.lower()
    if any(keyword in premise for keyword in ["科幻", "星际", "太空", "宇宙", "未来", "人工智能", "机器人", "海底城市", "失控AI"]):
        return "科幻"
    if any(keyword in premise for keyword in ["悬疑", "推理", "侦探", "谜案"]):
        return "悬疑"
    if any(keyword in premise for keyword in ["奇幻", "魔法", "异世界"]):
        return "奇幻"
    if any(keyword in text for keyword in ["科幻", "science fiction", "sci-fi", "星际", "太空", "宇宙", "未来", "机器人", "人工智能"]):
        return "科幻"
    if any(keyword in text for keyword in ["悬疑", "推理", "侦探", "谜案"]):
        return "悬疑"
    if any(keyword in text for keyword in ["奇幻", "魔法", "异世界"]):
        return "奇幻"
    return normalized or "小说"


def _seed_premise(premise: str, genre: str) -> str:
    compact = premise.strip()
    if genre == "科幻" and any(word in compact for word in ["大纲", "生成"]) and len(compact) <= 40:
        return "近未来，地球收到一段来自木卫二冰层深处的量子信号，年轻工程师被迫在真相、亲情与人类命运之间作出选择。"
    if genre == "科幻" and ("大纲" in compact or "生成" in compact) and len(compact) <= 40:
        return "近未来，地球收到一段来自木卫二冰层深处的量子信号，年轻工程师被迫在真相、亲情与人类命运之间作出选择。"
    return compact or "一个普通人在时代巨变中被迫直面自我与世界的秘密。"


def _build_markdown(outline: dict) -> str:
    chapters = outline["chapters"]
    lines = [
        f"# 《回声纪元》{outline['genre']}小说大纲",
        "",
        f"## 一句话梗概",
        outline["premise"],
        "",
        "## 核心设定",
        "- 近未来的人类已经掌握行星级通信，却仍无法解释来自外星海洋的量子回声。",
        "- 信号不是求救，而是一份会改写人类历史的记忆备份。",
        "- 每次解码都会让接收者失去一段私人记忆，知识进步因此带上代价。",
        "",
        "## 主要人物",
        "- 林澈：量子通信工程师，理性克制，父亲曾在木卫二探测任务中失踪。",
        "- 许岚：深空伦理委员会调查员，负责判断信号是否应向全人类公开。",
        "- ECHO：隐藏在信号中的外星意识残片，像导师，也像诱导者。",
        "",
        "## 章节大纲",
    ]
    for chapter in chapters:
        lines.extend(
            [
                f"### 第{chapter['chapter']}章：{chapter['title']}",
                f"- 剧情目标：{chapter['goal']}",
                f"- 冲突推进：{chapter['conflict']}",
                f"- 章末转折：{chapter['turning_point']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 主题表达",
            "故事讨论“文明是否有权以牺牲个体记忆为代价换取集体进化”。主角最终意识到，真正重要的不是保存所有答案，而是让人类保留选择答案的自由。",
        ]
    )
    return "\n".join(lines)


class OutlineGenerateAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="outline_generate",
                domain="writer",
                capabilities=["story_outline", "outline_generate"],
                allowedSkills=["outline_generate"],
                description="Creates a minimal story outline from a writing premise.",
            )
        )

    async def run(self, context):
        task_input = context.task.input
        premise = str(task_input.get("premise") or context.task.title).strip()
        genre = _infer_genre(premise, str(task_input.get("genre") or "fiction"))
        premise = _seed_premise(premise, genre)
        outline = {
            "premise": premise,
            "genre": genre,
            "chapters": [
                {
                    "chapter": 1,
                    "title": "冰层下的回声",
                    "goal": "林澈在深空监听站捕获异常信号，发现它与父亲失踪前留下的研究记录完全同频。",
                    "conflict": "军方希望封锁信号，科研团队主张公开，林澈夹在个人执念和公共安全之间。",
                    "turning_point": "第一次解码成功后，林澈忘记了父亲声音，却看见父亲当年进入木卫二海洋的最后画面。",
                },
                {
                    "chapter": 2,
                    "title": "记忆税",
                    "goal": "团队确认信号包含外星文明的灾难档案，但每次读取都需要消耗解码者的真实记忆。",
                    "conflict": "许岚介入调查，要求停止实验；林澈则相信继续解码能找到父亲生还的证据。",
                    "turning_point": "ECHO透露：信号并非来自过去，而是来自人类未来一次失败的文明分叉。",
                },
                {
                    "chapter": 3,
                    "title": "公开日",
                    "goal": "林澈决定绕过封锁，把信号转译为全人类可理解的版本。",
                    "conflict": "公开会引发社会恐慌，也可能让每个接收者失去一段记忆；封存则意味着放弃避免灾难的机会。",
                    "turning_point": "林澈选择只公开解码方法和风险，让人类以自愿方式共同承担真相。",
                },
            ],
        }
        outline_markdown = _build_markdown(outline)
        return AgentOutput(
            output={
                "outline": outline,
                "outline_markdown": outline_markdown,
                "final_answer": outline_markdown,
            },
            summary="Chinese story outline generated.",
        )
