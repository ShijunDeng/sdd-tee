执行下面的任务，任务组之间依次串行执行，任务组内的任务可以并行执行。

任务组1：
    任务1：使用环境上的cursor(启动命令是agent)进行下一轮测试，测试前修改cursor的model为GPT-5.4 1M Extra High
    任务2：使用环境上的gemini进行下一轮测试；测试前修改gemini的model为gemini-3.1-pro
    任务3：使用环境上的opencode进行下一轮测试，测试前修改opencode的model为MiniMax M2.5
任务组2：
    任务1：使用环境上的cursor(启动命令是agent)进行下一轮测试，测试前修改cursor的model为Opus 4.5 Thinking
    任务2：使用环境上的opencode进行下一轮测试，测试前修改opencode的model为Qwen3.5 Plus

任务组3：
    任务1：使用环境上的cursor(启动命令是agent)进行下一轮测试，测试前修改cursor的model为Grok 4.20 Thinking
    任务2：使用环境上的opencode进行下一轮测试，测试前修改opencode的model为glm-5

任务组4：
    任务1：使用环境上的cursor(启动命令是agent)进行下一轮测试，测试前修改cursor的model为Composer 2
    任务2：使用环境上的opencode进行下一轮测试，测试前修改opencode的model为glm-4.7

任务组5：
     任务1：整体审视测试结果的合理性，不同轮次的测试，各项指标应该是不一样的。测试数据与业界类似的测评不应该有非常大的出入；对于有异常或者怀疑的数据要在测试报告标明；对比报告要参考之前的报告，有详尽的总体分析，后面再列出对比数据


