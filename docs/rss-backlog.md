# RSS 订阅源后备清单
# 已验证可达但暂不适合加入 feeds.yaml 的源
# 后续扩展时可参考

blocked_by_gfw:
  - name: Google DeepMind
    url: https://deepmind.google/blog/rss.xml
    category: ai
    note: 英文 AI 前沿研究，国内被墙
  - name: Hacker News
    url: https://news.ycombinator.com/bigrss
    category: tech
    note: 科技社区，国内被墙，可走 RSSHub
  - name: Hugging Face Blog
    url: https://huggingface.co/blog/feed.xml
    category: ai
    note: 国内被墙（已有 HfDailyPapersCollector 走 API）
  - name: V2EX
    url: https://www.v2ex.com/index.xml
    category: tech
    note: 中文技术社区，国内被墙，可走 RSSHub
  - name: 阮一峰的网络日志
    url: https://www.ruanyifeng.com/blog/atom.xml
    category: tech
    note: 中文科技博客，国内被墙，可走 RSSHub

blocked_by_cdn:
  - name: TechSpot
    url: https://www.techspot.com/rss/
    category: tech
    note: Cloudflare 403 拦截
  - name: EE Times
    url: https://www.eetimes.com/feed/
    category: hardware
    note: CDN 403 拦截

ssl_or_format_issues:
  - name: Google AI Blog
    url: https://blog.google/technology/ai/rss/
    category: ai
    note: SSL 异常（unexpected EOF）
  - name: AnandTech
    url: https://www.anandtech.com/rss/
    category: hardware
    note: 返回 HTML 非 RSS，需自定义解析器

too_niche_for_now:
  - name: Chips and Cheese
    url: https://chipsandcheese.com/feed/
    category: hardware
    note: 芯片架构深度分析，受众窄
  - name: arXiv AI / ML
    url: https://rss.arxiv.org/rss/cs.AI
    category: ai
    note: 学术论文量大（每日几十篇），冲淡新闻感

third_party_proxy:
  - name: 机器之心(官方)
    url: https://www.jiqizhixin.com/rss
    category: ai
    note: 官方 RSS 返回 HTML SPA，不可用。当前用 RSSBox 代理
