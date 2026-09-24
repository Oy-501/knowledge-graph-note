# 软件工程领域高密度桥接知识库

> 本知识库用于支撑跨知识点桥接推理，每个条目包含：术语名、关联实体数组、桥接原文（用于悬浮溯源展示）。
> 解析格式：每条以 `## ` 开头，`related_entities:` `bridge_sentence:` `domain:` 字段各占一行。

<!-- ============================================================ -->
<!-- programming_paradigm -->
<!-- ============================================================ -->

## 面向对象编程 (OOP)
- related_entities: [封装, 继承, 多态, 抽象类, 接口, 设计模式, 面向对象]
- bridge_sentence: 面向对象编程以封装、继承、多态三大特性组织代码结构，是工厂、单例等设计模式得以落地的基石。
- domain: programming_paradigm

## 封装
- related_entities: [面向对象编程, 继承, 多态, 类, 私有字段, 访问修饰符, 信息隐藏]
- bridge_sentence: 封装将数据与操作绑定并隐藏内部实现，通过访问修饰符实现信息隐藏，是面向对象编程的根基。
- domain: programming_paradigm

## 继承
- related_entities: [封装, 多态, 面向对象编程, 抽象类, 接口, 子类, 父类, 复用]
- bridge_sentence: 继承允许子类复用父类的字段与方法，是 OOP 实现代码复用与层次抽象的关键机制。
- domain: programming_paradigm

## 多态
- related_entities: [继承, 接口, 重写, 重载, 动态绑定, 面向对象编程, 虚函数]
- bridge_sentence: 多态通过动态绑定让同一接口呈现不同行为，使面向对象系统能灵活扩展而不修改老代码。
- domain: programming_paradigm

## 抽象类
- related_entities: [接口, 继承, 多态, 模板方法, 抽象方法, 面向对象编程]
- bridge_sentence: 抽象类定义通用骨架并延迟具体实现到子类，桥接接口契约与具体实现之间的鸿沟。
- domain: programming_paradigm

## 接口
- related_entities: [抽象类, 多态, 实现类, 契约, 解耦, 面向对象编程, 依赖倒置]
- bridge_sentence: 接口以契约为先实现解耦，是依赖倒置、面向切面、微服务 API 设计共同依赖的抽象边界。
- domain: programming_paradigm

## 设计模式
- related_entities: [工厂模式, 单例模式, 观察者模式, 策略模式, 装饰器模式, 面向对象编程, 最佳实践]
- bridge_sentence: 设计模式是面向对象编程经验的结晶，工厂、单例、观察者等模式提供可复用的问题解法。
- domain: programming_paradigm

## 工厂模式
- related_entities: [单例模式, 抽象类, 接口, 创建对象, 依赖倒置, 设计模式, 面向对象编程]
- bridge_sentence: 工厂模式通过统一创建接口隐藏对象实例化细节，与单例模式同为面向对象创建型设计模式。
- domain: programming_paradigm

## 单例模式
- related_entities: [工厂模式, 全局唯一, 线程安全, 双重检查锁, 设计模式, 懒加载, 配置管理]
- bridge_sentence: 单例模式保证全局唯一实例，常用于配置管理、日志、线程池等共享资源，依赖双重检查锁保障线程安全。
- domain: programming_paradigm

## 观察者模式
- related_entities: [发布订阅, 事件驱动, Kafka, 消息队列, 回调函数, 设计模式]
- bridge_sentence: 观察者模式是事件驱动、Kafka 消息队列等发布订阅机制的抽象原型，将生产者与消费者解耦。
- domain: programming_paradigm

## 策略模式
- related_entities: [接口, 多态, 算法, 算法优化, 设计模式, 算法选择]
- bridge_sentence: 策略模式借助接口与多态封装可替换算法，是面向对象处理算法优化选择的标准范式。
- domain: programming_paradigm

## 代理模式
- related_entities: [AOP, 动态代理, 静态代理, Spring, 接口, 装饰器模式, 设计模式]
- bridge_sentence: 代理模式为对象附加横切逻辑，是 AOP 动态代理与 Spring 装饰器模式的共同设计原型。
- domain: programming_paradigm

## 装饰器模式
- related_entities: [代理模式, 设计模式, 接口, AOP, 责任链, IO 流, 面向对象编程]
- bridge_sentence: 装饰器模式层层包装对象扩展职责，与代理模式同属结构型设计模式，Java IO 流是其典型应用。
- domain: programming_paradigm

## 责任链模式
- related_entities: [装饰器模式, 代理模式, 后端网关, 鉴权, 过滤器, AOP, 设计模式]
- bridge_sentence: 责任链模式将请求沿链传递，是后端网关鉴权、过滤器与 AOP 拦截器的常用设计模式。
- domain: programming_paradigm

## 模板方法模式
- related_entities: [抽象类, 继承, 设计模式, 策略模式, 钩子函数, 算法骨架]
- bridge_sentence: 模板方法模式在抽象类中定义算法骨架，通过钩子函数让子类定制步骤，是继承实现算法复用的经典范式。
- domain: programming_paradigm

## 适配器模式
- related_entities: [接口, 设计模式, 装饰器模式, 代理模式, 兼容层, 微服务架构]
- bridge_sentence: 适配器模式通过接口转换兼容不匹配的组件，是微服务架构中集成异构系统的常用结构型设计模式。
- domain: programming_paradigm

## 建造者模式
- related_entities: [工厂模式, 设计模式, 构造器, 流式 API, 复杂对象, 面向对象编程]
- bridge_sentence: 建造者模式分步构造复杂对象，常以流式 API 呈现，与工厂模式互补处理对象创建的精细控制。
- domain: programming_paradigm

## 组合模式
- related_entities: [设计模式, 二叉树, 递归, 文件系统, 树形结构, 面向对象编程]
- bridge_sentence: 组合模式以树形结构统一处理叶子与组合节点，递归遍历是其核心操作，与二叉树共用数据结构思想。
- domain: programming_paradigm

## 命令模式
- related_entities: [设计模式, 异步任务, 消息队列, 撤销, 日志, 回调函数]
- bridge_sentence: 命令模式将请求封装为对象，是实现异步任务调度、消息队列处理与日志回放的常用设计模式。
- domain: programming_paradigm

## 状态模式
- related_entities: [设计模式, 策略模式, 有限状态机, 状态转移, 多态, 面向对象编程]
- bridge_sentence: 状态模式在对象内部状态变化时切换行为，与策略模式结构相似但意图不同，依赖有限状态机建模。
- domain: programming_paradigm

## 迭代器模式
- related_entities: [设计模式, 数据结构, 集合, 遍历, 二叉树, 接口, 面向对象编程]
- bridge_sentence: 迭代器模式以统一接口遍历集合，屏蔽底层数据结构差异，是二叉树、链表等容器遍历的标准方式。
- domain: programming_paradigm

## 领域驱动设计 (DDD)
- related_entities: [实体, 值对象, 聚合根, 仓储, 限界上下文, 微服务, 面向对象编程, 接口]
- bridge_sentence: 领域驱动设计以实体、值对象、聚合根为核心，限界上下文常对应微服务边界，将 OOP 思想延伸到业务架构层。
- domain: programming_paradigm

## 聚合根
- related_entities: [领域驱动设计, 实体, 值对象, 仓储, 一致性边界, 微服务]
- bridge_sentence: 聚合根是 DDD 中保证一致性的入口实体，其边界常作为微服务拆分依据。
- domain: programming_paradigm

## 限界上下文
- related_entities: [领域驱动设计, 聚合根, 微服务, 服务拆分, 接口, 上下文映射]
- bridge_sentence: 限界上下文为 DDD 划分模型边界，是微服务服务拆分与接口契约设计的高层依据。
- domain: programming_paradigm

## 实体
- related_entities: [领域驱动设计, 值对象, 聚合根, 仓储, 唯一标识, 持久化, 微服务]
- bridge_sentence: 实体是 DDD 中具有唯一标识的领域对象，与值对象共同构成聚合根内部的核心建模单元。
- domain: programming_paradigm

## 值对象
- related_entities: [领域驱动设计, 实体, 不可变性, 聚合根, 函数式编程, 面向对象编程]
- bridge_sentence: 值对象以属性值定义相等性且不可变，是 DDD 与函数式编程在不可变建模思想上的交汇点。
- domain: programming_paradigm

## 仓储 (Repository)
- related_entities: [领域驱动设计, 聚合根, 持久化, 数据库查询, ORM, 依赖注入, 接口]
- bridge_sentence: 仓储以接口隔离领域层与持久化层，是 DDD 中聚合根持久化与数据库查询的统一入口。
- domain: programming_paradigm

## 函数式编程
- related_entities: [纯函数, 不可变性, 高阶函数, 柯里化, 面向对象编程, 响应式编程, Java Stream]
- bridge_sentence: 函数式编程以纯函数与不可变数据为核心，与面向对象编程互补，Java Stream 与响应式编程均受其影响。
- domain: programming_paradigm

## 纯函数
- related_entities: [函数式编程, 不可变性, 副作用, 单元测试, 缓存, 幂等性]
- bridge_sentence: 纯函数对相同输入永远返回相同输出且无副作用，是函数式编程、单元测试与幂等性设计的根基。
- domain: programming_paradigm

## 高阶函数
- related_entities: [函数式编程, 回调函数, 柯里化, 装饰器模式, 策略模式, 响应式编程]
- bridge_sentence: 高阶函数以函数作为参数或返回值，是实现回调、装饰器模式与策略模式在函数式编程中的等价表达。
- domain: programming_paradigm

## 不可变性
- related_entities: [函数式编程, 值对象, 纯函数, 线程安全, 并发编程, 持久化数据结构]
- bridge_sentence: 不可变性禁止原地修改数据，是函数式编程、值对象建模与并发编程中线程安全设计的共同原则。
- domain: programming_paradigm

## 响应式编程
- related_entities: [函数式编程, 观察者模式, 异步任务, 数据流, 事件驱动, Vue, React]
- bridge_sentence: 响应式编程以数据流与变化传播为核心，桥接观察者模式与异步任务，是 Vue 与 React 响应式系统的思想源头。
- domain: programming_paradigm

## CQRS
- related_entities: [领域驱动设计, 事件溯源, 微服务架构, 读写分离, 消息队列, Kafka, 聚合根]
- bridge_sentence: CQRS 将读写模型分离，与事件溯源配合实现跨微服务异步同步，是 DDD 到微服务架构的关键桥接模式。
- domain: programming_paradigm

## 事件溯源
- related_entities: [CQRS, 领域驱动设计, 消息队列, Kafka, 聚合根, 持久化, 审计日志]
- bridge_sentence: 事件溯源以事件流记录所有状态变更，与 CQRS 协同实现状态回溯，依赖 Kafka 消息队列持久化事件。
- domain: programming_paradigm

## SOLID 原则
- related_entities: [面向对象编程, 设计模式, 接口, 依赖倒置, 依赖注入, 抽象类, 多态]
- bridge_sentence: SOLID 原则是面向对象设计的五大准则，依赖倒置与接口隔离直接导向依赖注入与设计模式的应用。
- domain: programming_paradigm

## 依赖倒置
- related_entities: [SOLID, 接口, 依赖注入, Spring, 抽象类, 解耦, 工厂模式]
- bridge_sentence: 依赖倒置要求高层不依赖低层而共同依赖抽象接口，是 Spring 依赖注入与工厂模式的设计原则基础。
- domain: programming_paradigm

<!-- ============================================================ -->
<!-- low_level -->
<!-- ============================================================ -->

## 虚拟内存
- related_entities: [操作系统, 内存管理, 分页, 交换分区, 内存映射, GC, 堆, 栈]
- bridge_sentence: 操作系统虚拟内存通过分页与交换分区隔离进程地址空间，是 GC 内存管理与堆栈数据结构的底层基础。
- domain: low_level

## 内存管理
- related_entities: [虚拟内存, 垃圾回收, 堆, 栈, 内存泄漏, 操作系统, 内存池, 引用计数]
- bridge_sentence: 内存管理衔接操作系统虚拟内存与编程语言 GC，统管堆栈分配、内存泄漏检测与引用计数。
- domain: low_level

## 垃圾回收 (GC)
- related_entities: [JVM, 标记清除, 引用计数, 分代收集, 内存泄漏, 堆, 内存管理, 虚拟内存]
- bridge_sentence: 垃圾回收是 JVM 等运行时自动管理内存的机制，依赖堆分区与分代收集策略，与虚拟内存协同避免内存泄漏。
- domain: low_level

## 标记清除算法
- related_entities: [垃圾回收, 分代收集, 内存碎片, 引用计数, JVM, 内存管理]
- bridge_sentence: 标记清除算法是 GC 的基础策略，配合分代收集提升 JVM 内存回收效率，但易产生内存碎片。
- domain: low_level

## 分代收集
- related_entities: [垃圾回收, 新生代, 老年代, 标记清除, JVM, 内存管理, 内存池]
- bridge_sentence: 分代收集按对象存活周期划分新生代与老年代，是 JVM GC 提升吞吐的核心优化策略。
- domain: low_level

## JVM 内存模型
- related_entities: [堆, 栈, 方法区, 程序计数器, 垃圾回收, 类加载, 内存管理, Java]
- bridge_sentence: JVM 内存模型将堆、栈、方法区划分管理，是 Java 垃圾回收与多线程内存可见性的运行时基础。
- domain: low_level

## 堆
- related_entities: [栈, 垃圾回收, 内存管理, 动态分配, 虚拟内存, 内存泄漏, JVM, 优先队列]
- bridge_sentence: 堆是动态分配的内存区域，由 GC 管理；同时也是一种优先队列数据结构，二者共享名字却语义不同。
- domain: low_level

## 栈
- related_entities: [堆, 函数调用, 局部变量, 递归, 虚拟内存, 内存管理, 方法调用栈, JVM]
- bridge_sentence: 栈用于函数调用与局部变量管理，与堆共同构成虚拟内存的两大核心区域，JVM 方法调用栈即基于此。
- domain: low_level

## 并发编程
- related_entities: [锁, 信号量, 线程, 互斥, 原子操作, 内存屏障, CAS, 线程池]
- bridge_sentence: 并发编程以锁与信号量协调多线程访问共享资源，是 JVM、操作系统内核都依赖的核心机制。
- domain: low_level

## 锁
- related_entities: [信号量, 互斥锁, 死锁, 并发编程, 线程安全, CAS, 自旋锁, 单例模式]
- bridge_sentence: 锁是并发编程保障线程安全的基石，单例模式的双重检查锁、自旋锁、CAS 均围绕其展开。
- domain: low_level

## 信号量
- related_entities: [锁, 互斥, 并发编程, 计数器, 同步原语, 操作系统, 资源池, 线程池]
- bridge_sentence: 信号量是操作系统提供的同步原语，通过计数器控制资源并发访问，是线程池与连接池容量控制的基础。
- domain: low_level

## 死锁
- related_entities: [锁, 信号量, 环形等待, 并发编程, 线程, 资源竞争, 互斥]
- bridge_sentence: 死锁源于并发编程中多线程相互持有对方所需锁，是并发设计必须规避的环形等待陷阱。
- domain: low_level

## 线程池
- related_entities: [信号量, 并发编程, 线程, 任务队列, 连接池, 资源池, 异步任务]
- bridge_sentence: 线程池预创建线程并复用，通过信号量控制并发数，是异步任务执行与连接池设计的共同思路。
- domain: low_level

## CAS 原子操作
- related_entities: [锁, 自旋锁, 并发编程, 原子操作, 内存屏障, ABA 问题, 无锁编程]
- bridge_sentence: CAS（Compare-And-Swap）是无锁编程的原子操作，与自旋锁配合规避锁开销，是并发编程底层基石。
- domain: low_level

## 内存屏障
- related_entities: [CAS, 并发编程, 指令重排, 可见性, JMM, JVM, 锁]
- bridge_sentence: 内存屏障禁止指令重排并保障可见性，是 CAS、锁与 JMM 协同保障并发正确性的关键。
- domain: low_level

## JMM (Java 内存模型)
- related_entities: [JVM 内存模型, 内存屏障, 并发编程, 可见性, happens-before, 锁, CAS]
- bridge_sentence: JMM 规定多线程间共享变量的可见性与 happens-before 关系，依赖内存屏障与锁实现。
- domain: low_level

## 类加载机制
- related_entities: [JVM 内存模型, 双亲委派, 字节码, 类加载器, Spring, 单例模式, 反射]
- bridge_sentence: 类加载机制以双亲委派模型加载字节码到 JVM，是 Spring 反射装配与单例模式初始化的底层前提。
- domain: low_level

## 内存泄漏
- related_entities: [垃圾回收, 内存管理, 堆, 引用计数, JVM, 连接池, 缓存]
- bridge_sentence: 内存泄漏源于引用未释放，使 GC 无法回收，需结合引用计数与连接池设计预防。
- domain: low_level

## 分布式锁
- related_entities: [锁, Redis, 信号量, 微服务架构, 一致性, Redlock, 事务]
- bridge_sentence: 分布式锁在微服务间借助 Redis 与 Redlock 实现互斥，是单机锁向多实例延伸的产物。
- domain: low_level

## 字节码
- related_entities: [类加载机制, JVM, 编译器, JIT 编译, 反射, 解释执行, Java]
- bridge_sentence: 字节码是 Java 编译器输出的中间表示，由 JVM 解释执行或 JIT 编译为机器码，是跨平台的基础。
- domain: low_level

## JIT 编译
- related_entities: [字节码, JVM, 编译器, 热点代码, 性能优化, AOT 编译, 解释执行]
- bridge_sentence: JIT 编译在运行时将热点字节码转为机器码，是 JVM 性能优化的核心手段，与 AOT 编译形成互补。
- domain: low_level

## 编译原理
- related_entities: [词法分析, 语法分析, 语义分析, 中间代码, 优化, 字节码, 编译器]
- bridge_sentence: 编译原理涵盖词法分析到目标代码生成全流程，是 JIT 编译、字节码转换与 LLVM 等编译器的理论基础。
- domain: low_level

## 内存池
- related_entities: [内存管理, 堆, 连接池, 线程池, 垃圾回收, 分配器, 性能优化]
- bridge_sentence: 内存池预分配内存块并复用，借鉴连接池与线程池思想，是减少 GC 压力与内存碎片的关键优化手段。
- domain: low_level

## 上下文切换
- related_entities: [进程调度, 线程, 并发编程, 协程, 性能优化, 操作系统, 中断]
- bridge_sentence: 上下文切换是线程与进程调度时保存恢复执行状态的开销，协程通过用户态切换减少此开销。
- domain: low_level

## 协程
- related_entities: [上下文切换, 线程, 异步任务, async/await, 并发编程, 栈, 状态机]
- bridge_sentence: 协程以用户态轻量切换替代内核级线程上下文切换，是异步任务 async/await 模型的底层执行单元。
- domain: low_level

## 零拷贝
- related_entities: [系统调用, 文件 IO, 网络通信, Kafka, 虚拟内存, 性能优化, mmap]
- bridge_sentence: 零拷贝绕过用户态与内核态之间的数据复制，Kafka 利用其提升网络 IO 性能，依赖 mmap 与 sendfile 系统调用。
- domain: low_level

## 用户态与内核态
- related_entities: [系统调用, 上下文切换, 虚拟内存, 中断, 零拷贝, 协程, 操作系统]
- bridge_sentence: 用户态与内核态的切换通过系统调用与中断触发，是上下文切换开销的根源，零拷贝与协程均致力于减少切换。
- domain: low_level

## 自旋锁
- related_entities: [锁, CAS, 互斥锁, 并发编程, 无锁编程, 线程, 上下文切换]
- bridge_sentence: 自旋锁以忙等代替阻塞，依赖 CAS 实现，避免上下文切换但消耗 CPU，适合临界区极短的并发场景。
- domain: low_level

## 读写锁
- related_entities: [锁, 自旋锁, 互斥锁, 并发编程, 读写分离, 数据库, 线程安全]
- bridge_sentence: 读写锁分离读锁与写锁，允许多读单写，是数据库读写分离与并发缓存设计中的常用锁机制。
- domain: low_level

<!-- ============================================================ -->
<!-- network -->
<!-- ============================================================ -->

## 浏览器 URL 输入
- related_entities: [DNS 解析, HTTP, TCP, 负载均衡, 前端渲染, 网络请求, 后端网关]
- bridge_sentence: 用户在浏览器输入 URL 后触发 DNS 解析、TCP 握手、HTTP 请求，经负载均衡最终抵达后端网关。
- domain: network

## DNS 解析
- related_entities: [浏览器 URL 输入, 域名, IP 地址, HTTP, TCP, UDP, 缓存]
- bridge_sentence: DNS 解析将域名映射到 IP 地址，是浏览器 URL 输入后网络全链路的第一步，结果常被多级缓存。
- domain: network

## TCP 三次握手
- related_entities: [DNS 解析, HTTP, TCP, 四次挥手, 拥塞控制, 可靠传输, 信号量]
- bridge_sentence: TCP 三次握手在 DNS 解析后建立可靠连接，是 HTTP/HTTPS 通信的前置条件，依赖序号与确认号同步。
- domain: network

## HTTP 协议
- related_entities: [HTTPS, TCP 三次握手, 请求方法, 状态码, 报文, Cookie, Session, RESTful]
- bridge_sentence: HTTP 协议构建在 TCP 三次握手之上，规定请求方法、状态码与报文结构，是前后端 RESTful 通信的核心契约。
- domain: network

## HTTPS
- related_entities: [HTTP, SSL/TLS, 证书, 加密, 证书颁发机构, 对称加密, 非对称加密]
- bridge_sentence: HTTPS 在 HTTP 之上叠加 SSL/TLS，借助非对称加密协商对称密钥，保障传输安全。
- domain: network

## 负载均衡
- related_entities: [HTTP, 后端网关, 反向代理, 轮询, 一致性哈希, 微服务, Nginx]
- bridge_sentence: 负载均衡在 HTTP 请求抵达后端网关前分发流量，常用 Nginx 反向代理实现轮询、一致性哈希等调度。
- domain: network

## 后端网关
- related_entities: [负载均衡, 微服务, API 网关, 鉴权, 限流, 路由, HTTP, 消息队列]
- bridge_sentence: 后端网关承接负载均衡后的请求，统一鉴权、限流、路由，再分发到具体微服务或消息队列。
- domain: network

## 数据库查询
- related_entities: [后端网关, SQL, 索引, 事务, 连接池, Redis 缓存, NoSQL]
- bridge_sentence: 数据库查询是后端网关处理请求的终点之一，依赖索引与连接池，结果常回写 Redis 缓存。
- domain: network

## 前端渲染
- related_entities: [浏览器 URL 输入, HTTP, HTML, CSS, JavaScript, 虚拟 DOM, 重排重绘]
- bridge_sentence: 前端渲染在浏览器 URL 输入与 HTTP 响应后展开，从 HTML、CSS 到 JavaScript 执行，依赖重排重绘完成视图更新。
- domain: network

## 虚拟 DOM
- related_entities: [前端渲染, React, Vue, 差异算法, 重排重绘, 框架, 性能优化]
- bridge_sentence: 虚拟 DOM 通过差异算法减少重排重绘，是 React、Vue 等前端框架渲染优化的核心抽象。
- domain: network

## 重排重绘
- related_entities: [虚拟 DOM, 前端渲染, 浏览器引擎, CSS, 性能优化, 布局]
- bridge_sentence: 重排重绘是浏览器引擎更新视图的高代价操作，虚拟 DOM 与 CSS 硬件加速共同致力于减少其触发。
- domain: network

## RESTful API
- related_entities: [HTTP, 资源, 状态码, 后端网关, 微服务架构, 接口, Spring]
- bridge_sentence: RESTful API 以 HTTP 方法映射资源操作，是后端网关与微服务对外暴露接口的常用风格。
- domain: network

## Cookie
- related_entities: [HTTP, Session, 鉴权, HTTPS, 同源策略, 前端渲染]
- bridge_sentence: Cookie 在 HTTP 协议下承载会话状态，与 Session 协同完成鉴权，需 HTTPS 与同源策略保障安全。
- domain: network

## Session
- related_entities: [Cookie, 鉴权, Redis 缓存, 分布式 Session, 微服务架构, 后端网关]
- bridge_sentence: Session 在服务端存储用户会话，常借助 Redis 缓存实现分布式 Session，适配微服务架构。
- domain: network

## 鉴权
- related_entities: [Session, Cookie, JWT, OAuth, 后端网关, 微服务架构, AOP, 接口]
- bridge_sentence: 鉴权由后端网关统一处理，结合 Session、JWT 或 OAuth 校验访问权限，是 AOP 横切关注点的典型场景。
- domain: network

## JWT
- related_entities: [鉴权, Token, 签名, HTTPS, 微服务架构, 后端网关, Session]
- bridge_sentence: JWT 以签名 Token 在客户端保存身份信息，无需服务端 Session，是微服务鉴权的轻量方案。
- domain: network

## TCP/IP 协议栈
- related_entities: [TCP 三次握手, HTTP, IP, 网络层, 传输层, 套接字, OSI 模型]
- bridge_sentence: TCP/IP 协议栈分四层从链路层到应用层，HTTP 位于应用层，TCP 在传输层，是互联网通信的骨架。
- domain: network

## UDP
- related_entities: [TCP/IP, DNS, QUIC, 无连接, 低延迟, 视频流, 实时通信]
- bridge_sentence: UDP 以无连接方式提供低延迟传输，DNS 解析与 QUIC 协议均基于其特性，适配实时音视频通信。
- domain: network

## WebSocket
- related_entities: [HTTP, 长连接, 全双工, 实时通信, 推送, 前端渲染, 服务器推送]
- bridge_sentence: WebSocket 在 HTTP 握手后升级为全双工长连接，是实时推送、聊天与在线协作的前端通信基石。
- domain: network

## gRPC
- related_entities: [HTTP/2, Protocol Buffers, 微服务架构, RESTful API, 接口, 后端网关, 服务发现]
- bridge_sentence: gRPC 基于 HTTP/2 与 Protocol Buffers 实现高性能 RPC，是微服务内部通信比 RESTful API 更高效的替代方案。
- domain: network

## GraphQL
- related_entities: [RESTful API, HTTP, 查询语言, 前端渲染, 后端网关, 接口, 微服务架构]
- bridge_sentence: GraphQL 以声明式查询语言替代 RESTful 多端点，让前端精确控制返回字段，是 API 网关聚合层的新范式。
- domain: network

## CDN
- related_entities: [DNS 解析, 负载均衡, 缓存, HTTP, HTTPS, 前端渲染, 静态资源]
- bridge_sentence: CDN 通过 DNS 解析将静态资源导向边缘节点，依赖负载均衡与缓存，是前端渲染加速的关键基础设施。
- domain: network

## OAuth 2.0
- related_entities: [鉴权, JWT, 授权码, 第三方登录, HTTPS, 微服务架构, 后端网关]
- bridge_sentence: OAuth 2.0 以授权码与 JWT 实现第三方鉴权，是微服务架构中统一认证与单点登录的标准协议。
- domain: network

## CORS
- related_entities: [HTTP, 同源策略, 前端渲染, 后端网关, 鉴权, 浏览器, 安全]
- bridge_sentence: CORS 是浏览器放宽同源策略的安全机制，通过 HTTP 头控制跨域资源访问，是前后端分离部署的必备配置。
- domain: network

## 限流
- related_entities: [后端网关, 信号量, 令牌桶, 漏桶算法, 高并发, 微服务架构, Redis]
- bridge_sentence: 限流在后端网关层以令牌桶或漏桶算法控制请求速率，依赖 Redis 实现分布式计数器，与信号量思想同源。
- domain: network

## 熔断
- related_entities: [限流, 微服务架构, 服务降级, 容错, 后端网关, 监控告警, 分布式系统]
- bridge_sentence: 熔断在微服务调用失败达到阈值时快速拒绝请求，与限流、服务降级共同构成分布式系统的容错三板斧。
- domain: network

## 服务降级
- related_entities: [熔断, 限流, 微服务架构, 容错, 兜底逻辑, 后端网关, 高可用]
- bridge_sentence: 服务降级在资源不足或依赖故障时提供兜底响应，与熔断协同保障微服务架构的高可用性。
- domain: network

## HTTP/2
- related_entities: [HTTP, gRPC, 多路复用, 头部压缩, HTTPS, TCP 三次握手, 性能优化]
- bridge_sentence: HTTP/2 以多路复用与头部压缩突破 HTTP 1.1 的并发瓶颈，是 gRPC 的底层传输协议。
- domain: network

## 反向代理
- related_entities: [负载均衡, Nginx, 后端网关, HTTP, HTTPS, 缓存, 安全]
- bridge_sentence: 反向代理以 Nginx 为代表，实现负载均衡、缓存与安全过滤，是后端网关的前置组件。
- domain: network

<!-- ============================================================ -->
<!-- data_flow -->
<!-- ============================================================ -->

## SQL 关系型数据库
- related_entities: [MySQL, 事务, 索引, B+ 树, ACID, NoSQL, Redis, 数据库查询]
- bridge_sentence: SQL 关系型数据库如 MySQL 通过 ACID 事务与 B+ 树索引提供强一致查询，是后端数据流转的源头。
- domain: data_flow

## NoSQL
- related_entities: [SQL 关系型数据库, MongoDB, Redis, 文档数据库, BASE, CAP, 水平扩展]
- bridge_sentence: NoSQL 以弱化 ACID 换取水平扩展能力，与 SQL 关系型数据库互补，常用于海量半结构化数据场景。
- domain: data_flow

## Redis 缓存
- related_entities: [SQL 关系型数据库, NoSQL, 缓存穿透, 缓存雪崩, 持久化, 内存管理, Kafka]
- bridge_sentence: Redis 缓存前置在 SQL 数据库之上，缓解热点查询压力，需警惕缓存穿透与缓存雪崩，并与 Kafka 协同削峰。
- domain: data_flow

## Kafka 消息队列
- related_entities: [Redis 缓存, 发布订阅, 观察者模式, 大数据流处理, 削峰, 异步任务, 主题分区]
- bridge_sentence: Kafka 以主题分区实现发布订阅，是观察者模式的工程化落地，连接 Redis 缓存与大数据流处理。
- domain: data_flow

## 大数据流处理
- related_entities: [Kafka, Spark Streaming, Flink, 窗口计算, 状态管理, 实时计算, 容错]
- bridge_sentence: 大数据流处理消费 Kafka 主题，依托 Spark Streaming 或 Flink 进行窗口计算与状态管理。
- domain: data_flow

## ACID
- related_entities: [SQL 关系型数据库, 事务, 原子性, 一致性, 隔离性, 持久性, CAP]
- bridge_sentence: ACID 是 SQL 关系型数据库事务的四大保证，与分布式 CAP 理论中的强一致分支相对应。
- domain: data_flow

## CAP 理论
- related_entities: [ACID, 一致性, 可用性, 分区容错, BASE, NoSQL, 微服务, 分布式系统]
- bridge_sentence: CAP 理论阐明分布式系统在一致性、可用性、分区容错间只能择二，是 NoSQL 与微服务架构权衡的依据。
- domain: data_flow

## BASE
- related_entities: [CAP, NoSQL, 最终一致性, ACID, 缓存, 分布式系统]
- bridge_sentence: BASE 选择最终一致性，是 NoSQL 在 CAP 权衡下相对 ACID 的折中策略。
- domain: data_flow

## 事务
- related_entities: [ACID, SQL 关系型数据库, 锁, 隔离级别, MVCC, 事务传播, Spring]
- bridge_sentence: 事务保障一组操作要么全部成功要么全部回滚，依赖锁与 MVCC 实现隔离，是 Spring 声明式事务的底层对象。
- domain: data_flow

## 索引
- related_entities: [SQL 关系型数据库, B+ 树, 哈希索引, 查询优化, 数据库查询, 慢查询, Redis 缓存]
- bridge_sentence: 索引以 B+ 树或哈希结构加速 SQL 查询，是数据库查询优化的核心手段，亦常与 Redis 缓存叠加使用。
- domain: data_flow

## B+ 树
- related_entities: [索引, 二叉树, 范围查询, 数据库索引, 磁盘 IO, MySQL, 数据结构]
- bridge_sentence: B+ 树以多叉平衡结构减少磁盘 IO，是 MySQL 索引与范围查询的数据结构基础。
- domain: data_flow

## 连接池
- related_entities: [线程池, 数据库查询, 资源池, 信号量, 频繁创建, 性能优化, Redis 缓存]
- bridge_sentence: 连接池复用数据库或 Redis 连接，借鉴线程池思路通过信号量控制并发，避免频繁创建销毁开销。
- domain: data_flow

## 一致性哈希
- related_entities: [负载均衡, 哈希表, 节点, 微服务架构, Redis, Kafka, 分布式系统]
- bridge_sentence: 一致性哈希在节点增删时最小化数据迁移，是负载均衡、Redis 分片与 Kafka 分区路由的共同算法。
- domain: data_flow

## 主题分区
- related_entities: [Kafka, 消息队列, 消费者组, 一致性哈希, 顺序消费, 发布订阅, 大数据流处理]
- bridge_sentence: 主题分区让 Kafka 并行扩展，消费者组按分区消费，是一致性哈希与发布订阅模式的工程化结合。
- domain: data_flow

## MVCC
- related_entities: [事务, 隔离级别, 锁, 快照读, 并发控制, SQL 关系型数据库, 回滚段]
- bridge_sentence: MVCC 以多版本快照实现无锁读，是 SQL 事务隔离级别与并发控制的核心机制，避免读写互斥阻塞。
- domain: data_flow

## 缓存穿透
- related_entities: [Redis 缓存, 缓存雪崩, 缓存击穿, 布隆过滤器, 空值缓存, SQL 关系型数据库]
- bridge_sentence: 缓存穿透针对查询不存在的数据绕过缓存直达数据库，布隆过滤器与空值缓存是其主要防御手段。
- domain: data_flow

## 缓存雪崩
- related_entities: [Redis 缓存, 缓存穿透, 缓存击穿, 过期时间, 高可用, 集群, 监控告警]
- bridge_sentence: 缓存雪崩因大量缓存同时过期导致请求涌入数据库，依赖过期时间随机化与 Redis 集群高可用应对。
- domain: data_flow

## 读写分离
- related_entities: [SQL 关系型数据库, 主从复制, 读写锁, 负载均衡, 数据一致性, 微服务架构]
- bridge_sentence: 读写分离将写操作路由主库、读操作路由从库，是读写锁思想在数据库架构中的规模化应用。
- domain: data_flow

## 分库分表
- related_entities: [读写分离, SQL 关系型数据库, 一致性哈希, 水平扩展, 路由, 分布式事务]
- bridge_sentence: 分库分表以一致性哈希或范围路由拆分数据，是关系型数据库水平扩展的终极方案，但引入分布式事务复杂度。
- domain: data_flow

## 布隆过滤器
- related_entities: [缓存穿透, 哈希函数, 位图, 概率数据结构, Redis, 去重, 空间效率]
- bridge_sentence: 布隆过滤器以位图与多哈希函数实现空间高效的集合判重，是防御缓存穿透与海量去重的关键数据结构。
- domain: data_flow

## 消息队列
- related_entities: [Kafka, RabbitMQ, 发布订阅, 点对点, 异步任务, 削峰, 解耦, 观察者模式]
- bridge_sentence: 消息队列以发布订阅或点对点模式实现异步解耦，是 Kafka 与 RabbitMQ 等中间件的抽象统称。
- domain: data_flow

## RabbitMQ
- related_entities: [消息队列, Kafka, AMQP, 交换机, 死信队列, 异步任务, 微服务架构]
- bridge_sentence: RabbitMQ 实现 AMQP 协议，以交换机路由消息，与 Kafka 互补，适合微服务内低延迟任务分发。
- domain: data_flow

## 死信队列
- related_entities: [RabbitMQ, 消息队列, Kafka, 重试, 异步任务, 监控告警, 容错]
- bridge_sentence: 死信队列收集无法正常消费的消息，是消息队列重试策略与监控告警的兜底机制。
- domain: data_flow

## 数据仓库
- related_entities: [OLAP, ETL, 大数据流处理, SQL 关系型数据库, BI, 维度建模, 列式存储]
- bridge_sentence: 数据仓库通过 ETL 汇聚业务库数据，采用列式存储与维度建模支撑 OLAP 分析，是 BI 报表的数据底座。
- domain: data_flow

## ETL
- related_entities: [数据仓库, 数据管道, 大数据流处理, Kafka, ELT, 数据清洗, 数据质量]
- bridge_sentence: ETL 从源系统抽取、转换、加载数据到数据仓库，与 ELT 的区别在于转换时机，是数据管道的前身。
- domain: data_flow

## 数据管道
- related_entities: [ETL, Kafka, 大数据流处理, 数据仓库, 实时计算, 批处理, CDC]
- bridge_sentence: 数据管道以 Kafka 为中枢串联 ETL 与流处理，将业务数据实时或批量输送到数据仓库。
- domain: data_flow

## CDC
- related_entities: [数据管道, 数据库, ETL, Kafka, 日志, 实时同步, 数据仓库]
- bridge_sentence: CDC 通过数据库日志捕获变更事件，经 Kafka 实时同步到下游系统，是数据管道与 ETL 的实时数据源。
- domain: data_flow

## 列式存储
- related_entities: [数据仓库, OLAP, 索引, Parquet, ORC, 压缩, SQL 关系型数据库]
- bridge_sentence: 列式存储按列组织数据以提升压缩率与聚合查询，是数据仓库、OLAP 引擎与 Parquet/ORC 格式的底层策略。
- domain: data_flow

## OLAP
- related_entities: [OLTP, 数据仓库, 列式存储, 多维分析, 索引, 大数据, BI]
- bridge_sentence: OLAP 面向多维分析查询，依赖列式存储与预计算索引，与 OLTP 的事务处理形成数据系统的两极。
- domain: data_flow

## OLTP
- related_entities: [OLAP, SQL 关系型数据库, 事务, ACID, 索引, 微服务, 高并发]
- bridge_sentence: OLTP 面向高并发事务处理，依赖 ACID 与行级索引，是微服务业务数据库的日常运行模式。
- domain: data_flow

## 查询优化
- related_entities: [索引, SQL, 执行计划, 慢查询, 性能优化, 数据结构, 连接池]
- bridge_sentence: 查询优化通过分析执行计划与索引选择提升 SQL 效率，是数据库性能优化的核心工程实践。
- domain: data_flow

## 分布式事务
- related_entities: [事务, ACID, CAP, BASE, 两阶段提交, SAGA, TCC, 微服务架构]
- bridge_sentence: 分布式事务在微服务跨库操作中保障一致性，两阶段提交、SAGA 与 TCC 是其三种主流实现模式。
- domain: data_flow

## SAGA 模式
- related_entities: [分布式事务, 微服务架构, 消息队列, Kafka, 补偿事务, 最终一致性, BASE]
- bridge_sentence: SAGA 模式以本地事务加补偿事务链实现最终一致性，依赖消息队列编排，是微服务分布式事务的常用方案。
- domain: data_flow

<!-- ============================================================ -->
<!-- framework -->
<!-- ============================================================ -->

## Spring 框架
- related_entities: [依赖注入, 面向切面编程, Bean, 事务, 微服务, Java, 控制反转, 接口]
- bridge_sentence: Spring 以依赖注入与面向切面编程为核心，统一 Bean 生命周期与声明式事务，是 Java 微服务架构的基础底座。
- domain: framework

## 依赖注入 (DI)
- related_entities: [Spring, 控制反转, Bean, 接口, 解耦, 面向对象编程, 装配]
- bridge_sentence: 依赖注入是 Spring IoC 容器的实现方式，借助接口与装配解耦对象创建，是 OOP 思想的工程化延展。
- domain: framework

## 面向切面编程 (AOP)
- related_entities: [Spring, 代理模式, 横切关注点, 事务, 日志, 鉴权, 动态代理]
- bridge_sentence: 面向切面编程通过动态代理横切事务、日志等通用逻辑，是 Spring 声明式事务与后端网关鉴权的底层模式。
- domain: framework

## 控制反转 (IoC)
- related_entities: [依赖注入, Spring, 容器, Bean, 接口, 装配, 解耦]
- bridge_sentence: 控制反转将对象创建权交由容器，是依赖注入的设计思想内核，使 Spring 实现解耦装配。
- domain: framework

## 微服务架构
- related_entities: [Spring, 限界上下文, 领域驱动设计, 后端网关, 服务发现, 配置中心, 容器化, Docker]
- bridge_sentence: 微服务架构将系统按限界上下文拆分，经后端网关统一入口，依赖服务发现与配置中心协同，常以 Docker 容器化部署。
- domain: framework

## 服务发现
- related_entities: [微服务架构, 注册中心, 负载均衡, 健康检查, Nacos, Eureka, 容器化]
- bridge_sentence: 服务发现通过注册中心维护微服务实例地址，配合负载均衡动态路由，是容器化部署的核心支撑。
- domain: framework

## 配置中心
- related_entities: [微服务架构, 服务发现, 动态配置, 热更新, 灰度发布, Nacos, 单例模式]
- bridge_sentence: 配置中心集中管理微服务的动态配置，支持热更新与灰度发布，常以单例模式暴露访问入口。
- domain: framework

## Docker 容器化
- related_entities: [微服务架构, 镜像, 容器, Linux 内核, 命名空间, Cgroups, 持续集成]
- bridge_sentence: Docker 容器化基于 Linux 内核命名空间与 Cgroups，将微服务及其依赖打包为镜像，支撑持续集成交付。
- domain: framework

## Kubernetes
- related_entities: [Docker, 容器编排, Pod, 服务发现, 负载均衡, 微服务架构, 声明式配置]
- bridge_sentence: Kubernetes 在 Docker 之上提供容器编排，以 Pod 为单位调度并集成服务发现与负载均衡。
- domain: framework

## 持续集成 (CI/CD)
- related_entities: [Docker, Kubernetes, 自动化测试, 流水线, 灰度发布, 微服务架构, 版本控制]
- bridge_sentence: 持续集成借助流水线、自动化测试与 Docker 打包，将微服务持续交付到 Kubernetes，是工程效率的保障。
- domain: framework

## Linux 内核
- related_entities: [操作系统, 虚拟内存, 进程调度, 文件系统, Docker, 命名空间, Cgroups, 系统调用]
- bridge_sentence: Linux 内核提供虚拟内存、进程调度、文件系统与命名空间，是 Docker 容器化与操作系统教学的共同根。
- domain: framework

## 进程调度
- related_entities: [Linux 内核, 线程, 并发编程, 上下文切换, 优先级, 时间片, 操作系统]
- bridge_sentence: 进程调度决定线程与进程的 CPU 时间分配，与并发编程中的上下文切换紧密相关。
- domain: framework

## 系统调用
- related_entities: [Linux 内核, 用户态, 内核态, 文件 IO, 网络通信, 信号量, 操作系统]
- bridge_sentence: 系统调用是用户态访问内核态资源的接口，文件 IO、网络通信与信号量均需经此进入内核。
- domain: framework

## 反射
- related_entities: [类加载机制, Spring, 依赖注入, 注解, 动态代理, AOP, Bean]
- bridge_sentence: 反射在运行期读取类信息，使 Spring 依赖注入、AOP 动态代理与 Bean 装配成为可能。
- domain: framework

## 日志
- related_entities: [AOP, 单例模式, 异步任务, 线程池, 文件 IO, 监控, 持久化]
- bridge_sentence: 日志常通过 AOP 横切记录，落地为文件 IO 或异步任务，单例模式管理 logger 实例。
- domain: framework

## 配置管理
- related_entities: [单例模式, 配置中心, 持久化, 热更新, 启动加载, JSON, YAML]
- bridge_sentence: 配置管理以单例模式加载 JSON/YAML 持久化参数，并通过配置中心实现热更新。
- domain: framework

## 持久化
- related_entities: [SQL 关系型数据库, Redis, 文件 IO, 日志, 配置管理, IndexedDB, LocalStorage]
- bridge_sentence: 持久化将内存状态写入 SQL 数据库、Redis 或文件，是日志、配置管理与前端 LocalStorage 的共同目标。
- domain: framework

## 异步任务
- related_entities: [线程池, 消息队列, Kafka, 回调, Promise, Future, 观察者模式]
- bridge_sentence: 异步任务依托线程池与消息队列实现非阻塞，前端 Promise、Future 与观察者模式是其抽象表达。
- domain: framework

## 单元测试
- related_entities: [持续集成, 自动化测试, Mock, 依赖注入, Spring, 测试覆盖率, 微服务架构]
- bridge_sentence: 单元测试依赖依赖注入完成 Mock，是持续集成流水线与自动化测试覆盖率的基石。
- domain: framework

## Mock
- related_entities: [单元测试, 依赖注入, 接口, 解耦, 测试替身, Spring, 微服务架构]
- bridge_sentence: Mock 借助接口与依赖注入替换真实依赖，是单元测试解耦后端微服务的常用手段。
- domain: framework

## 监控告警
- related_entities: [日志, 微服务架构, Prometheus, 指标, 阈值, 异步任务, 线程池]
- bridge_sentence: 监控告警采集日志与指标，配合阈值触发，是微服务架构下保障线程池与异步任务稳定的耳目。
- domain: framework

## Spring Boot
- related_entities: [Spring, 自动配置, 起步依赖, 嵌入式容器, 微服务架构, 配置中心, 监控]
- bridge_sentence: Spring Boot 以自动配置与起步依赖简化 Spring 应用搭建，内嵌 Tomcat，是微服务架构的快速启动器。
- domain: framework

## Spring Cloud
- related_entities: [Spring Boot, 微服务架构, 服务发现, 配置中心, 后端网关, 负载均衡, 熔断]
- bridge_sentence: Spring Cloud 在 Spring Boot 之上集成服务发现、配置中心与熔断，是 Java 微服务全家桶的一站式方案。
- domain: framework

## Spring Security
- related_entities: [Spring, 鉴权, OAuth, JWT, 过滤器链, 后端网关, AOP]
- bridge_sentence: Spring Security 以过滤器链拦截请求，集成 OAuth 与 JWT，是 Spring 生态中鉴权与授权的标准组件。
- domain: framework

## MyBatis
- related_entities: [ORM, SQL, 数据库查询, Spring, JDBC, 动态 SQL, 连接池]
- bridge_sentence: MyBatis 以 XML 或注解映射 SQL 与 Java 对象，是介于 JDBC 与全自动 ORM 之间的半自动持久化框架。
- domain: framework

## ORM
- related_entities: [MyBatis, Hibernate, JPA, SQL, 数据库查询, 持久化, 对象映射]
- bridge_sentence: ORM 将数据库表映射为对象，Hibernate 是全自动代表，MyBatis 是半自动代表，是持久化层的核心抽象。
- domain: framework

## 声明式事务
- related_entities: [Spring, AOP, 事务, 代理模式, 事务传播, 回滚, 注解]
- bridge_sentence: 声明式事务是 Spring AOP 的典型应用，通过注解声明事务边界，依赖动态代理实现事务传播与回滚。
- domain: framework

## Nginx
- related_entities: [反向代理, 负载均衡, 后端网关, HTTP, HTTPS, 静态资源, CDN]
- bridge_sentence: Nginx 以反向代理实现负载均衡与静态资源服务，是后端网关与 CDN 边缘节点的核心组件。
- domain: framework

## Prometheus
- related_entities: [监控告警, Grafana, 指标, 时序数据库, 微服务架构, Kubernetes, 拉取模式]
- bridge_sentence: Prometheus 以拉取模式采集时序指标，与 Grafana 配合可视化，是 Kubernetes 微服务监控的事实标准。
- domain: framework

## Grafana
- related_entities: [Prometheus, 监控告警, 仪表盘, 可视化, 时序数据, 日志, 告警规则]
- bridge_sentence: Grafana 将 Prometheus 指标与日志数据可视化，以仪表盘与告警规则呈现，是监控系统的展示层。
- domain: framework

## OpenTelemetry
- related_entities: [分布式追踪, Jaeger, Zipkin, 日志, 指标, 微服务架构, 监控告警]
- bridge_sentence: OpenTelemetry 统一分布式追踪、日志与指标采集标准，是 Jaeger 与 Zipkin 等追踪系统的数据来源。
- domain: framework

## Terraform
- related_entities: [IaC, Kubernetes, Docker, 云原生, 声明式配置, 基础设施, CI/CD]
- bridge_sentence: Terraform 以声明式配置管理云基础设施，是 IaC 的核心工具，与 Kubernetes 声明式编排思想一脉相承。
- domain: framework

## Helm
- related_entities: [Kubernetes, 模板, 包管理, 声明式配置, 微服务架构, CI/CD, 配置管理]
- bridge_sentence: Helm 以模板化 Chart 打包 Kubernetes 资源，是 K8s 的包管理器，与配置中心协同管理微服务部署。
- domain: framework

## 服务网格
- related_entities: [微服务架构, Istio, Envoy, 边车, 流量管理, 安全, 可观测性]
- bridge_sentence: 服务网格以边车代理将通信逻辑从业务代码中剥离，是微服务架构中流量管理与可观测性的基础设施层。
- domain: framework

## 灰度发布
- related_entities: [微服务架构, Kubernetes, 服务网格, 配置中心, 蓝绿部署, 金丝雀发布, CI/CD]
- bridge_sentence: 灰度发布逐步将新版本流量切给小部分用户，依赖服务网格流量管理与配置中心动态路由实现。
- domain: framework

## 自动化测试
- related_entities: [单元测试, 集成测试, 端到端测试, CI/CD, Mock, 测试覆盖率, 回归测试]
- bridge_sentence: 自动化测试覆盖单元、集成与端到端三层，是 CI/CD 流水线的质量关卡，依赖 Mock 隔离外部依赖。
- domain: framework

<!-- ============================================================ -->
<!-- algorithm -->
<!-- ============================================================ -->

## 算法优化
- related_entities: [时间复杂度, 空间复杂度, 动态规划, 贪心算法, 分治, 策略模式, 数据结构]
- bridge_sentence: 算法优化以时间复杂度与空间复杂度为目标，借助动态规划、贪心与分治等策略，与策略模式互为表里。
- domain: algorithm

## 动态规划
- related_entities: [算法优化, 状态转移, 重叠子问题, 分治, 递归, 记忆化搜索, 数据结构]
- bridge_sentence: 动态规划通过状态转移与记忆化搜索解决重叠子问题，是算法优化中分治思想的延伸。
- domain: algorithm

## 贪心算法
- related_entities: [算法优化, 局部最优, 全局最优, 动态规划, 策略模式, 数据结构]
- bridge_sentence: 贪心算法以局部最优推全局最优，相较动态规划更轻量但需谨慎证明正确性，是策略模式的一种体现。
- domain: algorithm

## 时间复杂度
- related_entities: [算法优化, 空间复杂度, 大 O 表示, 数据结构, 索引, 排序, 性能优化]
- bridge_sentence: 时间复杂度用大 O 表示衡量算法效率，是评估索引、排序与数据结构选择的核心标尺。
- domain: algorithm

## 空间复杂度
- related_entities: [时间复杂度, 算法优化, 内存管理, 数据结构, 堆, 栈]
- bridge_sentence: 空间复杂度衡量算法占用的内存规模，与时间复杂度共同构成算法优化的双轴评价。
- domain: algorithm

## 排序算法
- related_entities: [时间复杂度, 快速排序, 归并排序, 堆排序, 数据结构, 算法优化, 分治]
- bridge_sentence: 排序算法包括快速排序、归并排序与堆排序，时间复杂度从 O(n²) 到 O(n log n)，是数据结构与算法优化的基础议题。
- domain: algorithm

## 哈希表
- related_entities: [索引, 哈希函数, 冲突解决, 链地址法, Redis, 字典, 数据结构, Map]
- bridge_sentence: 哈希表通过哈希函数与冲突解决策略实现 O(1) 查询，是 Redis、Map 与索引的底层结构。
- domain: algorithm

## 二叉树
- related_entities: [B+ 树, 二叉搜索树, 平衡二叉树, 红黑树, 数据结构, 递归, 遍历]
- bridge_sentence: 二叉树是 B+ 树与红黑树的祖先结构，承载递归遍历与平衡算法，是数据结构教学的核心。
- domain: algorithm

## 图
- related_entities: [深度优先搜索, 广度优先搜索, 拓扑排序, 最短路径, 数据结构, 邻接矩阵, PageRank]
- bridge_sentence: 图以顶点与边表达关系，深度优先与广度优先是其基本遍历，PageRank 即图中心度算法的代表作。
- domain: algorithm

## PageRank
- related_entities: [图, 中心度, 节点, 入度, 出度, 推荐系统, 拓扑排序]
- bridge_sentence: PageRank 通过入度与出度衡量图节点中心度，是孤儿收养机制选取 Top5 核心节点的算法原型。
- domain: algorithm

## 深度优先搜索 (DFS)
- related_entities: [图, 广度优先搜索, 递归, 栈, 数据结构, 拓扑排序]
- bridge_sentence: 深度优先搜索借助递归与栈遍历图结构，是拓扑排序与连通分量判定的基础算法。
- domain: algorithm

## 广度优先搜索 (BFS)
- related_entities: [图, 深度优先搜索, 队列, 最短路径, 数据结构, 层次遍历]
- bridge_sentence: 广度优先搜索借助队列逐层扩展，是无权图最短路径与层次遍历的核心算法。
- domain: algorithm

## 性能优化
- related_entities: [索引, 缓存, 连接池, 算法优化, 时间复杂度, 空间复杂度, 虚拟 DOM, 重排重绘]
- bridge_sentence: 性能优化横跨索引、缓存、连接池、算法优化与前端虚拟 DOM，是全链路工程能力的综合体现。
- domain: algorithm

## 数据结构
- related_entities: [算法优化, 堆, 栈, 哈希表, 二叉树, 图, B+ 树, 时间复杂度]
- bridge_sentence: 数据结构涵盖堆、栈、哈希表、二叉树、图与 B+ 树，是算法优化与时间复杂度评估的物质基础。
- domain: algorithm

## 递归
- related_entities: [栈, 二叉树, 深度优先搜索, 动态规划, 分治, 函数调用, 算法优化]
- bridge_sentence: 递归依赖栈机制展开，是二叉树遍历、深度优先搜索、分治与动态规划等算法的共同骨架。
- domain: algorithm

## 分治
- related_entities: [递归, 动态规划, 快速排序, 归并排序, 二叉树, 算法优化, 数据结构]
- bridge_sentence: 分治将大问题拆为同构子问题，是快速排序、归并排序与二叉树递归遍历的共同思想。
- domain: algorithm

## 快速排序
- related_entities: [排序算法, 分治, 递归, 时间复杂度, 数据结构, 枢轴, 原地排序]
- bridge_sentence: 快速排序以分治递归选枢轴分区，平均 O(n log n)，是排序算法中工程实践最广泛的实现。
- domain: algorithm

## 归并排序
- related_entities: [排序算法, 分治, 递归, 快速排序, 外部排序, 稳定排序, 时间复杂度]
- bridge_sentence: 归并排序以分治合并两个有序序列，是稳定排序与外部排序的首选，时间 O(n log n) 且空间 O(n)。
- domain: algorithm

## 堆排序
- related_entities: [排序算法, 堆, 优先队列, 二叉树, 时间复杂度, 选择排序, 数据结构]
- bridge_sentence: 堆排序基于堆数据结构实现选择排序，O(n log n) 且原地排序，是优先队列的底层实现。
- domain: algorithm

## 红黑树
- related_entities: [二叉树, 平衡二叉树, 哈希表, TreeMap, 自平衡, 插入, 删除, 旋转]
- bridge_sentence: 红黑树以颜色约束实现自平衡二叉搜索树，是 Java TreeMap 与 Linux 内核调度器的底层数据结构。
- domain: algorithm

## 二分查找
- related_entities: [排序算法, 时间复杂度, 有序数组, 索引, 二叉搜索树, 算法优化, 数据结构]
- bridge_sentence: 二分查找在有序数组中 O(log n) 定位目标，是索引与二叉搜索树查找思想的简化原型。
- domain: algorithm

## 最短路径
- related_entities: [图, Dijkstra, BFS, 动态规划, 贪心, 导航, 网络路由]
- bridge_sentence: 最短路径算法以 Dijkstra 或 BFS 求解图中两点最优路由，是网络路由协议与导航系统的核心算法。
- domain: algorithm

## Dijkstra 算法
- related_entities: [最短路径, 图, 贪心算法, 优先队列, 堆, 网络路由, BFS]
- bridge_sentence: Dijkstra 算法以贪心优先队列求解非负权图最短路径，是网络路由协议 OSPF 的底层算法。
- domain: algorithm

## 拓扑排序
- related_entities: [图, 深度优先搜索, BFS, 有向无环图, 依赖解析, 任务调度, 数据结构]
- bridge_sentence: 拓扑排序对有向无环图排序节点，依赖 DFS 或 BFS，是构建工具依赖解析与任务调度的算法基础。
- domain: algorithm

## 并查集
- related_entities: [图, 最小生成树, Kruskal, 连通分量, 哈希表, 路径压缩, 按秩合并]
- bridge_sentence: 并查集以路径压缩与按秩合并高效维护集合合并与查询，是 Kruskal 最小生成树与连通分量的核心数据结构。
- domain: algorithm

## 最小生成树
- related_entities: [图, 并查集, Kruskal, Prim, 贪心算法, 网络拓扑, 数据结构]
- bridge_sentence: 最小生成树以 Kruskal 或 Prim 算法求图的最小连通代价，是网络拓扑规划与聚类分析的底层算法。
- domain: algorithm

## 字符串匹配
- related_entities: [KMP, 子串查找, 索引, 哈希表, 算法优化, 正则表达式, 搜索引擎]
- bridge_sentence: 字符串匹配算法如 KMP 以 O(n+m) 完成子串查找，是搜索引擎索引与正则表达式引擎的底层实现。
- domain: algorithm

## 跳表
- related_entities: [哈希表, 红黑树, Redis, 有序集合, 二分查找, 链表, 概率数据结构]
- bridge_sentence: 跳表以多层链表实现 O(log n) 的有序查找，是 Redis 有序集合的底层数据结构，与红黑树功能等价。
- domain: algorithm

## LRU 缓存
- related_entities: [哈希表, 链表, Redis, 缓存, 淘汰策略, 内存管理, 数据结构]
- bridge_sentence: LRU 缓存以哈希表加双向链表实现最近最少使用淘汰，是 Redis 内存淘汰与操作系统页面置换的标准策略。
- domain: algorithm

<!-- ============================================================ -->
<!-- ai_ml -->
<!-- ============================================================ -->

## 机器学习
- related_entities: [深度学习, 监督学习, 无监督学习, 强化学习, 神经网络, 算法优化, 数据]
- bridge_sentence: 机器学习以数据驱动模型学习，涵盖监督到强化学习，是深度学习与 LLM 的学科基础。
- domain: ai_ml

## 深度学习
- related_entities: [机器学习, 神经网络, CNN, RNN, Transformer, 反向传播, GPU]
- bridge_sentence: 深度学习以多层神经网络与反向传播突破传统机器学习瓶颈，是 CNN、RNN 与 Transformer 的技术底座。
- domain: ai_ml

## 神经网络
- related_entities: [深度学习, 感知机, 激活函数, 反向传播, 梯度下降, 算法优化, 损失函数]
- bridge_sentence: 神经网络模拟生物神经元连接，通过反向传播与梯度下降优化权重，是深度学习的计算模型核心。
- domain: ai_ml

## CNN
- related_entities: [深度学习, 卷积, 池化, 图像识别, 计算机视觉, 特征提取, 神经网络]
- bridge_sentence: CNN 以卷积与池化提取图像空间特征，是计算机视觉图像识别与目标检测的基准模型。
- domain: ai_ml

## RNN
- related_entities: [深度学习, LSTM, GRU, 序列数据, 时序, NLP, Transformer, 神经网络]
- bridge_sentence: RNN 以循环结构处理序列数据，LSTM 与 GRU 解决长距依赖，是 NLP 与 Transformer 之前的主流序列模型。
- domain: ai_ml

## Transformer
- related_entities: [深度学习, 注意力机制, 自注意力, BERT, GPT, LLM, NLP, 编码器解码器]
- bridge_sentence: Transformer 以自注意力机制替代 RNN 的循环结构，是 BERT、GPT 等 LLM 的架构基础，引爆 NLP 革命。
- domain: ai_ml

## 注意力机制
- related_entities: [Transformer, 自注意力, 多头注意力, 编码器解码器, 查询键值, 深度学习, NLP]
- bridge_sentence: 注意力机制以查询-键-值三元组计算上下文权重，自注意力是 Transformer 的核心，使模型关注输入序列的关键部分。
- domain: ai_ml

## LLM
- related_entities: [Transformer, GPT, 预训练, 微调, 提示工程, RAG, 嵌入, 深度学习]
- bridge_sentence: LLM 基于 Transformer 以海量文本预训练，支持提示工程、微调与 RAG 等下游任务，是当前 AI 的核心范式。
- domain: ai_ml

## GPT
- related_entities: [LLM, Transformer, 自回归, 预训练, 提示工程, 微调, 深度学习]
- bridge_sentence: GPT 以自回归 Transformer 解码器架构生成文本，是 LLM 的标杆模型，依赖预训练与提示工程落地。
- domain: ai_ml

## BERT
- related_entities: [Transformer, 编码器, 预训练, 微调, NLP, 掩码语言模型, 文本分类]
- bridge_sentence: BERT 以 Transformer 编码器与掩码语言模型实现双向理解，是 NLP 文本分类与命名实体识别的预训练基石。
- domain: ai_ml

## 提示工程
- related_entities: [LLM, GPT, 少样本学习, 思维链, 上下文学习, RAG, 微调]
- bridge_sentence: 提示工程通过精心构造输入引导 LLM 输出，是少样本学习与思维链推理的前置技能，与 RAG 互补。
- domain: ai_ml

## 微调
- related_entities: [LLM, 预训练, 提示工程, PEFT, LoRA, 迁移学习, 深度学习]
- bridge_sentence: 微调在预训练 LLM 上以小数据调整参数，LoRA 等 PEFT 方法低资源高效微调，是 LLM 落地的关键步骤。
- domain: ai_ml

## LoRA
- related_entities: [微调, PEFT, LLM, 低秩分解, 迁移学习, 深度学习, 参数高效]
- bridge_sentence: LoRA 以低秩矩阵分解实现参数高效微调，大幅降低 LLM 微调成本，是 PEFT 中最流行的技术。
- domain: ai_ml

## RAG
- related_entities: [LLM, 嵌入, 向量数据库, 检索增强, 提示工程, 知识库, 语义搜索]
- bridge_sentence: RAG 在 LLM 推理前检索外部知识库，将检索结果融入提示上下文，是缓解 LLM 幻觉的实用架构。
- domain: ai_ml

## 嵌入 (Embedding)
- related_entities: [向量, 语义搜索, RAG, 向量数据库, 相似度, LLM, NLP]
- bridge_sentence: 嵌入将文本映射为语义向量，余弦相似度衡量语义距离，是 RAG 检索与向量数据库相似度搜索的基础。
- domain: ai_ml

## 向量数据库
- related_entities: [嵌入, RAG, 语义搜索, ANN, FAISS, 相似度, 检索, 知识库]
- bridge_sentence: 向量数据库以 ANN 索引加速嵌入向量的相似度搜索，是 RAG 检索增强与语义搜索的存储引擎。
- domain: ai_ml

## 监督学习
- related_entities: [机器学习, 无监督学习, 回归, 分类, 标注数据, 损失函数, 算法优化]
- bridge_sentence: 监督学习依赖标注数据训练回归或分类模型，以损失函数衡量误差，与无监督学习共同构成机器学习的两大分支。
- domain: ai_ml

## 无监督学习
- related_entities: [机器学习, 监督学习, 聚类, 降维, 嵌入, 自编码器, 深度学习]
- bridge_sentence: 无监督学习从无标注数据中发现模式，聚类与降维是典型任务，是嵌入与自编码器的基础思想。
- domain: ai_ml

## 强化学习
- related_entities: [机器学习, 策略, 奖励, 环境, 深度学习, 搜索, 博弈]
- bridge_sentence: 强化学习以试错与奖励信号优化策略，与深度学习结合的 DRL 是 AlphaGo 与 RLHF 的核心技术。
- domain: ai_ml

## RLHF
- related_entities: [强化学习, LLM, 人类反馈, 微调, GPT, 奖励模型, 对齐]
- bridge_sentence: RLHF 以人类偏好训练奖励模型指导 LLM 微调，是 GPT 对齐人类价值观的关键技术。
- domain: ai_ml

## 计算机视觉
- related_entities: [CNN, 深度学习, 图像识别, 目标检测, 分割, GAN, 扩散模型]
- bridge_sentence: 计算机视觉以 CNN 与深度学习处理图像，涵盖识别、检测与分割，GAN 与扩散模型进一步拓展到生成。
- domain: ai_ml

## 目标检测
- related_entities: [计算机视觉, CNN, YOLO, 图像识别, 深度学习, 边界框, 分割]
- bridge_sentence: 目标检测以 YOLO 等模型定位并分类图像中的物体，边界框回归是核心，是计算机视觉的关键任务。
- domain: ai_ml

## NLP
- related_entities: [深度学习, Transformer, BERT, 文本分类, 情感分析, 机器翻译, 命名实体识别]
- bridge_sentence: NLP 以 Transformer 与 BERT 处理自然语言，涵盖分类、翻译与命名实体识别，是 LLM 的应用领域。
- domain: ai_ml

## 语义搜索
- related_entities: [嵌入, 向量数据库, RAG, 相似度, 知识库, LLM, NLP]
- bridge_sentence: 语义搜索以嵌入向量相似度替代关键词匹配，是 RAG 检索增强与向量数据库的核心应用场景。
- domain: ai_ml

## 思维链
- related_entities: [提示工程, LLM, 推理, 少样本学习, 复杂任务, 分治, 逻辑]
- bridge_sentence: 思维链引导 LLM 分步推理，是提示工程中的高级技巧，将复杂任务分解为逻辑步骤链。
- domain: ai_ml

## Agent
- related_entities: [LLM, 工具调用, 函数调用, 思维链, 规划, 记忆, 多智能体]
- bridge_sentence: Agent 以 LLM 为大脑，结合工具调用与规划，能自主完成多步任务，是 LLM 从对话到行动的进化方向。
- domain: ai_ml

## 函数调用 (Function Calling)
- related_entities: [Agent, LLM, 工具调用, API, 插件, 微服务, 接口]
- bridge_sentence: 函数调用让 LLM 按结构化接口触发外部 API 与工具，是 Agent 与环境交互的核心机制。
- domain: ai_ml

## 扩散模型
- related_entities: [深度学习, 图像生成, GAN, Stable Diffusion, 计算机视觉, 概率模型, 噪声]
- bridge_sentence: 扩散模型通过逐步去噪生成图像，是 Stable Diffusion 与 DALL-E 等图像生成模型的底层技术。
- domain: ai_ml

## GAN
- related_entities: [深度学习, 生成器, 判别器, 对抗训练, 图像生成, 扩散模型, 计算机视觉]
- bridge_sentence: GAN 以生成器与判别器对抗训练生成逼真图像，是扩散模型之前图像生成的主流范式。
- domain: ai_ml

## 迁移学习
- related_entities: [微调, 预训练, 深度学习, 监督学习, LLM, 特征提取, 领域自适应]
- bridge_sentence: 迁移学习将在源域学到的知识迁移到目标域，微调 LLM 是迁移学习在大模型时代的典型应用。
- domain: ai_ml

<!-- ============================================================ -->
<!-- frontend -->
<!-- ============================================================ -->

## HTML
- related_entities: [CSS, JavaScript, DOM, 前端渲染, 浏览器, 语义化, 虚拟 DOM]
- bridge_sentence: HTML 构建网页的语义化骨架，与 CSS 负责样式、JavaScript 负责交互，三者共同构成前端渲染的基石。
- domain: frontend

## CSS
- related_entities: [HTML, JavaScript, 样式, 布局, 响应式设计, 重排重绘, 虚拟 DOM]
- bridge_sentence: CSS 控制 HTML 样式与布局，其属性变更触发重排重绘，是虚拟 DOM 与响应式设计优化的核心目标。
- domain: frontend

## JavaScript
- related_entities: [HTML, CSS, DOM, 事件循环, 异步任务, 闭包, 前端渲染, TypeScript]
- bridge_sentence: JavaScript 是浏览器端唯一原生编程语言，操控 DOM 与事件循环，是前端框架与异步任务的基础。
- domain: frontend

## TypeScript
- related_entities: [JavaScript, 类型系统, 接口, 编译, 前端框架, 重构, 工具链]
- bridge_sentence: TypeScript 为 JavaScript 添加静态类型系统，通过接口约束提升代码质量，是大型前端项目的标配语言。
- domain: frontend

## DOM
- related_entities: [HTML, JavaScript, 虚拟 DOM, 前端渲染, 事件, 操作, 浏览器引擎]
- bridge_sentence: DOM 是浏览器解析 HTML 后构建的树形节点模型，JavaScript 操作 DOM 触发渲染更新，是虚拟 DOM 要优化的对象。
- domain: frontend

## 事件循环
- related_entities: [JavaScript, 异步任务, 微任务, 宏任务, Promise, 浏览器渲染, Node.js]
- bridge_sentence: 事件循环是 JavaScript 的异步执行模型，以微任务与宏任务队列调度回调，是前端异步任务的核心机制。
- domain: frontend

## Promise
- related_entities: [异步任务, 事件循环, 回调, async/await, 微任务, 观察者模式, 响应式编程]
- bridge_sentence: Promise 以链式调用管理异步操作状态，是事件循环中微任务的来源，async/await 是其语法糖。
- domain: frontend

## React
- related_entities: [虚拟 DOM, Vue, 声明式, 组件化, JSX, Hooks, 状态管理, 前端框架]
- bridge_sentence: React 以虚拟 DOM 与声明式组件化构建 UI，Hooks 管理状态，与 Vue 同为主流前端框架。
- domain: frontend

## Vue
- related_entities: [虚拟 DOM, React, 响应式, 组件化, 模板, 组合式 API, 状态管理, 前端框架]
- bridge_sentence: Vue 以响应式数据绑定与虚拟 DOM 构建 UI，组合式 API 管组织逻辑，与 React 共同主导前端开发生态。
- domain: frontend

## 状态管理
- related_entities: [Vue, React, Redux, Pinia, Vuex, 响应式编程, 观察者模式, 组件化]
- bridge_sentence: 状态管理以集中式 Store 统管跨组件共享状态，Redux 与 Pinia 是其代表，依赖观察者模式通知更新。
- domain: frontend

## 响应式设计
- related_entities: [CSS, 媒体查询, Flexbox, Grid, 视口, 移动优先, 多端适配]
- bridge_sentence: 响应式设计以媒体查询与 Flexbox/Grid 布局适配不同视口，是从移动优先到多端统一的前端布局策略。
- domain: frontend

## Webpack
- related_entities: [Vite, 打包, 模块化, 代码分割, 热更新, 前端工程化, 构建工具]
- bridge_sentence: Webpack 以模块打包与代码分割构建前端资源，是 Vite 之前的构建工具标准，驱动前端工程化。
- domain: frontend

## Vite
- related_entities: [Webpack, esbuild, 热更新, 开发服务器, 前端工程化, 构建工具, 模块化]
- bridge_sentence: Vite 基于 esbuild 实现极速冷启动与热更新，是 Webpack 的下一代替代者，已成为 Vue 与 React 的默认构建工具。
- domain: frontend

## SSR
- related_entities: [前端渲染, React, Vue, Next.js, Nuxt, SEO, 首屏, 虚拟 DOM]
- bridge_sentence: SSR 在服务端预先渲染 HTML 返回客户端，提升首屏速度与 SEO，是 Next.js 与 Nuxt 的核心能力。
- domain: frontend

## 浏览器渲染引擎
- related_entities: [DOM, CSSOM, 渲染树, 重排重绘, 合成, GPU, 前端渲染]
- bridge_sentence: 浏览器渲染引擎从 DOM 与 CSSOM 构建渲染树，经布局、绘制与合成三步显示页面，是前端渲染的底层执行者。
- domain: frontend

## 代码分割
- related_entities: [Webpack, Vite, 懒加载, 模块化, 性能优化, 前端工程化, 首屏]
- bridge_sentence: 代码分割将应用拆为按需加载的块，减少首屏体积，是 Webpack 与 Vite 性能优化的核心策略。
- domain: frontend

## 闭包
- related_entities: [JavaScript, 作用域, 函数式编程, 高阶函数, 柯里化, 模块化, 内存泄漏]
- bridge_sentence: 闭包让函数捕获其词法作用域，是 JavaScript 高阶函数与模块化的基石，但不当使用会引发内存泄漏。
- domain: frontend

## WebAssembly
- related_entities: [JavaScript, 浏览器, 性能优化, 编译, 字节码, 前端, 沙箱]
- bridge_sentence: WebAssembly 让浏览器运行编译后的字节码，性能接近原生，是 JavaScript 在计算密集型场景的有效补充。
- domain: frontend

<!-- ============================================================ -->
<!-- backend -->
<!-- ============================================================ -->

## 认证 (Authentication)
- related_entities: [鉴权, 授权, JWT, OAuth, Session, Cookie, 后端网关, 微服务架构]
- bridge_sentence: 认证验证用户身份，依赖 JWT 或 Session，是鉴权与授权的前置步骤，由后端网关统一处理。
- domain: backend

## 授权 (Authorization)
- related_entities: [认证, 鉴权, RBAC, ABAC, OAuth, 权限, 后端网关, 微服务架构]
- bridge_sentence: 授权在认证后决定用户可访问资源，RBAC 以角色为粒度、ABAC 以属性为粒度，是微服务权限模型的核心。
- domain: backend

## RBAC
- related_entities: [授权, ABAC, 角色, 权限, 鉴权, 后端网关, 微服务架构, 安全]
- bridge_sentence: RBAC 以角色关联权限，简化授权管理，是后端微服务权限设计的主流模型。
- domain: backend

## 单点登录 (SSO)
- related_entities: [认证, OAuth, JWT, Session, 鉴权, CAS, 微服务架构, 后端网关]
- bridge_sentence: 单点登录以 OAuth 或 CAS 实现一次登录多系统通行，是微服务架构下统一认证的核心方案。
- domain: backend

## API 版本管理
- related_entities: [RESTful API, 后端网关, 微服务架构, 接口, 兼容, 灰度发布, 配置管理]
- bridge_sentence: API 版本管理以 URL 路径或请求头区分版本，是微服务接口演进时保持向后兼容的标准实践。
- domain: backend

## 幂等性
- related_entities: [API, 分布式事务, 消息队列, 纯函数, 重试, 后端网关, 并发编程]
- bridge_sentence: 幂等性保证多次相同请求结果一致，是分布式事务、消息队列重试与 API 安全设计的核心原则。
- domain: backend

## 分布式追踪
- related_entities: [OpenTelemetry, Jaeger, 微服务架构, 调用链, 监控告警, 日志, 后端网关]
- bridge_sentence: 分布式追踪以 Trace ID 串联微服务调用链，依赖 OpenTelemetry 采集，是微服务排障的关键可观测性手段。
- domain: backend

## 数据库设计
- related_entities: [SQL 关系型数据库, 范式, 反范式, 索引, 事务, ER 模型, 微服务架构]
- bridge_sentence: 数据库设计以 ER 建模与范式规范化，平衡读写性能与一致性，是微服务数据架构的基础工程。
- domain: backend

## 范式
- related_entities: [数据库设计, 反范式, SQL 关系型数据库, 冗余, 事务, 数据一致性, 索引]
- bridge_sentence: 范式通过消除冗余保障数据一致性，反范式以可控冗余换取查询性能，是数据库设计的核心权衡。
- domain: backend

## Raft
- related_entities: [分布式系统, 一致性, 共识算法, 选举, 日志复制, 分布式锁, 微服务架构]
- bridge_sentence: Raft 以领导选举与日志复制实现分布式共识，是 etcd 与 TiKV 等分布式系统一致性保障的底层算法。
- domain: backend

## 分布式 ID
- related_entities: [分布式系统, Snowflake, UUID, 数据库, 微服务架构, 分库分表, 唯一性]
- bridge_sentence: 分布式 ID 以 Snowflake 或 UUID 在微服务分库分表场景下生成全局唯一标识，是分布式系统的基础设施。
- domain: backend

## 事件驱动架构
- related_entities: [消息队列, Kafka, 观察者模式, CQRS, 异步任务, 微服务架构, 解耦]
- bridge_sentence: 事件驱动架构以事件消息异步串联微服务，依赖 Kafka 消息队列，是观察者模式在分布式系统中的架构级实现。
- domain: backend

<!-- ============================================================ -->
<!-- devops -->
<!-- ============================================================ -->

## DevOps
- related_entities: [CI/CD, 监控告警, 基础设施即代码, Docker, Kubernetes, 微服务架构, 自动化]
- bridge_sentence: DevOps 以 CI/CD 与 IaC 打通开发运维壁垒，是微服务架构从代码到生产的全链路自动化方法论。
- domain: devops

## 基础设施即代码 (IaC)
- related_entities: [Terraform, DevOps, Kubernetes, CI/CD, 声明式配置, 版本控制, 云原生]
- bridge_sentence: 基础设施即代码以声明式配置版本化管理云资源，Terraform 是其代表，是 DevOps 的基础工程实践。
- domain: devops

## 容器编排
- related_entities: [Kubernetes, Docker, 微服务架构, 服务发现, 负载均衡, 自动伸缩, 故障恢复]
- bridge_sentence: 容器编排以 Kubernetes 为核心，调度 Docker 容器，集成服务发现与自动伸缩，是微服务部署的标配。
- domain: devops

## 蓝绿部署
- related_entities: [灰度发布, 金丝雀发布, Kubernetes, CI/CD, 微服务架构, 零停机, 负载均衡]
- bridge_sentence: 蓝绿部署以新旧两套环境一键切换，是微服务零停机发布的经典策略，与金丝雀发布互补。
- domain: devops

## 金丝雀发布
- related_entities: [蓝绿部署, 灰度发布, Kubernetes, 服务网格, 流量管理, 监控告警, CI/CD]
- bridge_sentence: 金丝雀发布逐步将小比例流量导到新版，依赖服务网格流量管理，是灰度发布最常用的实现方式。
- domain: devops

## 日志聚合
- related_entities: [ELK, Loki, 日志, 监控告警, 微服务架构, 分布式追踪, 全文搜索]
- bridge_sentence: 日志聚合以 ELK 或 Loki 集中收集微服务分布式日志，支持全文搜索，是故障排查的可观测性支柱。
- domain: devops

## ELK
- related_entities: [日志聚合, Elasticsearch, Logstash, Kibana, 监控告警, 全文搜索, DevOps]
- bridge_sentence: ELK 以 Elasticsearch 存储、Logstash 采集、Kibana 可视化，是日志聚合与监控告警的经典技术栈。
- domain: devops

## GitOps
- related_entities: [Git, CI/CD, Kubernetes, ArgoCD, 声明式配置, 版本控制, DevOps]
- bridge_sentence: GitOps 以 Git 仓库为单一事实来源驱动 Kubernetes 部署，ArgoCD 是其代表，是声明式配置的 DevOps 实践。
- domain: devops

## 混沌工程
- related_entities: [容错, 微服务架构, 高可用, 熔断, 服务降级, 监控告警, DevOps]
- bridge_sentence: 混沌工程以主动注入故障验证系统韧性，与熔断与服务降级互补，是微服务高可用性的压力测试方法。
- domain: devops

## SLO
- related_entities: [SLA, SLI, 监控告警, 错误预算, 高可用, 微服务架构, DevOps]
- bridge_sentence: SLO 定义服务可接受的质量指标，SLI 是实际测量值，SLA 是契约承诺，三者是 SRE 运维的核心度量。
- domain: devops

## 自动伸缩
- related_entities: [Kubernetes, HPA, 容器编排, 监控告警, 负载均衡, 微服务架构, 性能优化]
- bridge_sentence: 自动伸缩以 HPA 根据 CPU 或自定义指标动态调整 Pod 数量，是 Kubernetes 应对流量波动的核心能力。
- domain: devops

## 密钥管理
- related_entities: [安全, Vault, 配置中心, 加密, 微服务架构, DevOps, Kubernetes]
- bridge_sentence: 密钥管理以 Vault 安全存储与轮换数据库密码、API Key 等敏感信息，是微服务安全配置的基础设施。
- domain: devops

<!-- ============================================================ -->
<!-- supplementary terms -->
<!-- ============================================================ -->

## 事件循环 (Event Loop)
- related_entities: [JavaScript, 异步任务, Promise, 微任务, 宏任务, 浏览器, Node.js]
- bridge_sentence: 事件循环是 JavaScript 运行时的核心调度机制，以微任务与宏任务队列管理异步回调，连接 Promise 与浏览器渲染。
- domain: frontend

## Flexbox
- related_entities: [CSS, 响应式设计, Grid, 布局, 前端渲染, 重排重绘, 视口适配]
- bridge_sentence: Flexbox 以一维弹性布局模型简化 CSS 对齐与分布，与 Grid 互补，是响应式设计中减少重排重绘的布局利器。
- domain: frontend

## 柯里化
- related_entities: [函数式编程, 高阶函数, 闭包, 纯函数, 部分应用, JavaScript, 不可变性]
- bridge_sentence: 柯里化将多参数函数转为单参数函数链，依赖闭包与高阶函数，是函数式编程的核心技巧。
- domain: programming_paradigm

## 享元模式
- related_entities: [设计模式, 内存池, 单例模式, 缓存, 内存管理, 对象池, 面向对象编程]
- bridge_sentence: 享元模式以共享减少对象创建数量，与内存池、单例模式共为内存优化型设计模式，常用于文本编辑器与缓存。
- domain: programming_paradigm

## 外观模式
- related_entities: [设计模式, 接口, 适配器模式, 后端网关, 解耦, 面向对象编程, 简化]
- bridge_sentence: 外观模式以统一接口封装复杂子系统，是后端网关对外暴露简化 API 的常用设计模式。
- domain: programming_paradigm

## 中介者模式
- related_entities: [设计模式, 观察者模式, 消息队列, 解耦, 事件驱动, 微服务架构, 面向对象编程]
- bridge_sentence: 中介者模式以中介对象协调组件通信，是消息队列与事件驱动架构在对象层面的设计原型。
- domain: programming_paradigm

## 访问者模式
- related_entities: [设计模式, 迭代器模式, 组合模式, 数据结构, 双分派, 算法, 面向对象编程]
- bridge_sentence: 访问者模式以双分派将算法与数据结构分离，与迭代器模式配合遍历组合结构，适合 AST 等复杂树形操作。
- domain: programming_paradigm

## 备忘录模式
- related_entities: [设计模式, 状态, 快照, 撤销, 持久化, 命令模式, 面向对象编程]
- bridge_sentence: 备忘录模式以快照保存对象状态，是实现撤销重做与状态持久化的设计模式，常与命令模式联合使用。
- domain: programming_paradigm

## 桥接模式
- related_entities: [设计模式, 抽象类, 接口, 适配器模式, 组合模式, 解耦, 面向对象编程]
- bridge_sentence: 桥接模式将抽象与实现分离为两套独立层次，通过组合桥接，与适配器模式同为结构型设计模式但意图不同。
- domain: programming_paradigm

## 原型模式
- related_entities: [设计模式, 克隆, 工厂模式, 单例模式, 对象创建, 原型链, 面向对象编程]
- bridge_sentence: 原型模式以克隆而非新建创建对象，是 JavaScript 原型链与 Java Cloneable 接口的设计基础。
- domain: programming_paradigm

## 六边形架构
- related_entities: [领域驱动设计, 接口, 依赖倒置, 微服务架构, 端口适配器, 解耦, 清洁架构]
- bridge_sentence: 六边形架构以端口与适配器隔离业务核心与外部依赖，是 DDD 与微服务架构中实现依赖倒置的架构模式。
- domain: programming_paradigm

## 清洁架构
- related_entities: [六边形架构, 领域驱动设计, 依赖倒置, SOLID, 微服务架构, 分层架构, 接口]
- bridge_sentence: 清洁架构以依赖规则将业务核心置于同心圆中心，是六边形架构与 SOLID 原则的架构级综合体现。
- domain: programming_paradigm

## 引用计数
- related_entities: [垃圾回收, 内存管理, 内存泄漏, 循环引用, 智能指针, 标记清除, 内存池]
- bridge_sentence: 引用计数以对象引用次数判断回收时机，是 GC 的补充策略，但循环引用导致内存泄漏，需标记清除兜底。
- domain: low_level

## 指令重排
- related_entities: [内存屏障, JMM, 并发编程, 编译器优化, 可见性, 有序性, CAS]
- bridge_sentence: 指令重排是编译器与 CPU 的性能优化，但破坏并发有序性，依赖内存屏障与 JMM 约束其可见性影响。
- domain: low_level

## 中断
- related_entities: [操作系统, 上下文切换, 系统调用, 进程调度, 信号, 用户态与内核态, 并发]
- bridge_sentence: 中断是硬件或软件触发内核态切换的机制，是上下文切换与进程调度的底层触发源。
- domain: low_level

## 内存映射 (mmap)
- related_entities: [虚拟内存, 文件 IO, 零拷贝, 共享内存, 系统调用, 内核态, 性能优化]
- bridge_sentence: mmap 将文件映射到虚拟内存实现零拷贝读写，是共享内存与高性能文件 IO 的底层机制。
- domain: low_level

## 共享内存
- related_entities: [mmap, 进程间通信, 虚拟内存, 并发编程, 信号量, 零拷贝, 操作系统]
- bridge_sentence: 共享内存允许多进程访问同一物理内存区域，依赖信号量同步，是最高效的进程间通信方式。
- domain: low_level

## 双亲委派模型
- related_entities: [类加载机制, JVM, 字节码, 类加载器, 安全, 命名空间, 反射]
- bridge_sentence: 双亲委派模型要求类加载器优先委派父加载器，是 JVM 类加载机制保证类唯一性与安全的核心设计。
- domain: low_level

## TLS/SSL
- related_entities: [HTTPS, 证书, 加密, 握手, 非对称加密, 对称加密, 证书颁发机构]
- bridge_sentence: TLS/SSL 在 TCP 之上建立加密通道，通过握手协商密钥，是 HTTPS 安全传输的协议层实现。
- domain: network

## QUIC
- related_entities: [UDP, HTTP/3, TLS, 多路复用, 低延迟, TCP, 拥塞控制]
- bridge_sentence: QUIC 基于 UDP 实现类 TCP 的可靠传输并内置 TLS，是 HTTP/3 的传输层，解决了 TCP 队头阻塞问题。
- domain: network

## 同源策略
- related_entities: [CORS, Cookie, 浏览器, 安全, 前端渲染, 跨域, Session]
- bridge_sentence: 同源策略是浏览器限制跨域脚本访问的安全基石，CORS 是其可控放宽机制，保护 Cookie 与 Session 安全。
- domain: network

## 缓存击穿
- related_entities: [Redis 缓存, 缓存穿透, 缓存雪崩, 互斥锁, 热点数据, 数据库, 分布式锁]
- bridge_sentence: 缓存击穿针对热点 key 过期瞬间大量请求涌入数据库，互斥锁与分布式锁是其主要防御手段。
- domain: data_flow

## 主从复制
- related_entities: [读写分离, SQL 关系型数据库, Redis, 数据一致性, 日志, 高可用, 分布式系统]
- bridge_sentence: 主从复制将主库写入同步到从库，是读写分离的基础，Redis 与 MySQL 均依赖其实现数据冗余与高可用。
- domain: data_flow

## 执行计划
- related_entities: [查询优化, 索引, SQL, 慢查询, 数据库查询, 性能优化, 数据结构]
- bridge_sentence: 执行计划是数据库优化器生成的查询步骤方案，通过 EXPLAIN 分析，是索引选择与 SQL 调优的直接依据。
- domain: data_flow

## 梯度下降
- related_entities: [神经网络, 反向传播, 深度学习, 优化, 损失函数, 学习率, 算法优化]
- bridge_sentence: 梯度下降沿损失函数梯度方向迭代更新参数，是神经网络反向传播训练的核心优化算法。
- domain: ai_ml

## 损失函数
- related_entities: [梯度下降, 神经网络, 监督学习, 深度学习, 优化, 交叉熵, 均方误差]
- bridge_sentence: 损失函数量化模型预测与真实值的偏差，是梯度下降优化的目标函数，交叉熵与均方误差是其常见形式。
- domain: ai_ml

## 反向传播
- related_entities: [梯度下降, 神经网络, 深度学习, 链式法则, 损失函数, 权重更新, 计算图]
- bridge_sentence: 反向传播以链式法则从输出层向输入层传播梯度，是神经网络梯度下降训练中计算各层梯度的核心算法。
- domain: ai_ml

## 过拟合
- related_entities: [机器学习, 正则化, 深度学习, 交叉验证, 泛化, 欠拟合, 早停]
- bridge_sentence: 过拟合使模型在训练集表现好但泛化差，正则化、交叉验证与早停是防止过拟合的常用手段。
- domain: ai_ml

## 正则化
- related_entities: [过拟合, 机器学习, L1, L2, Dropout, 深度学习, 损失函数]
- bridge_sentence: 正则化以 L1/L2 约束或 Dropout 随机失活防止过拟合，是机器学习与深度学习模型泛化的关键技巧。
- domain: ai_ml

## 分词 (Tokenization)
- related_entities: [NLP, LLM, 嵌入, BPE, WordPiece, 文本预处理, 词汇表]
- bridge_sentence: 分词将文本切分为 token 序列，BPE 与 WordPiece 是主流算法，是 LLM 嵌入与 NLP 预处理的入口环节。
- domain: ai_ml

## 模型量化
- related_entities: [LLM, 推理, 性能优化, 精度, 深度学习, 模型部署, 边缘计算]
- bridge_sentence: 模型量化以低精度数值表示权重，是 LLM 推理加速与边缘部署的核心优化，牺牲少量精度换取大幅性能提升。
- domain: ai_ml

## 懒加载
- related_entities: [代码分割, 性能优化, 前端渲染, Webpack, Vite, 单例模式, 按需加载]
- bridge_sentence: 懒加载将非首屏资源延迟加载，与代码分割搭配实现按需加载，是前端性能优化与单例模式延迟初始化的共同思路。
- domain: frontend

## 热更新 (HMR)
- related_entities: [Webpack, Vite, 开发体验, 前端工程化, 虚拟 DOM, 模块化, 构建工具]
- bridge_sentence: 热更新在开发时局部替换模块而不刷新页面，依赖 Webpack 或 Vite 的模块热替换机制，是前端开发体验的关键。
- domain: frontend

## Service Worker
- related_entities: [PWA, 浏览器, 缓存, 离线, 前端渲染, Web Worker, 网络请求]
- bridge_sentence: Service Worker 在浏览器后台拦截网络请求并缓存资源，是 PWA 离线可用与前端性能优化的核心能力。
- domain: frontend

## 微前端
- related_entities: [微服务架构, 模块联邦, 前端工程化, 代码分割, 解耦, 部署, 独立开发]
- bridge_sentence: 微前端将前端应用拆为独立部署的子应用，借鉴微服务架构思想，是大型前端项目的解耦与工程化方案。
- domain: frontend

## 数据库索引
- related_entities: [索引, B+ 树, 哈希索引, 查询优化, 聚簇索引, 非聚簇索引, 覆盖索引]
- bridge_sentence: 数据库索引以 B+ 树或哈希结构加速查询，聚簇索引决定物理存储顺序，是查询优化与执行计划的核心引用对象。
- domain: backend

## 隔离级别
- related_entities: [事务, ACID, MVCC, 锁, 脏读, 幻读, 不可重复读, SQL 关系型数据库]
- bridge_sentence: 隔离级别定义事务间可见性，从读未提交到可串行化，依赖 MVCC 与锁实现，是数据库并发控制的核心配置。
- domain: backend

## 分布式会话
- related_entities: [Session, Redis, 微服务架构, 鉴权, 负载均衡, 一致性哈希, 粘性会话]
- bridge_sentence: 分布式会话以 Redis 集中存储 Session 解决微服务多实例间会话共享，是一致性哈希负载均衡的常见配合方案。
- domain: backend

## 高可用 (HA)
- related_entities: [熔断, 服务降级, 限流, 负载均衡, 冗余, 故障转移, 监控告警, Kubernetes]
- bridge_sentence: 高可用以冗余、故障转移与熔断限流保障系统持续运行，是微服务架构与 Kubernetes 集群设计的核心目标。
- domain: backend

## 服务注册中心
- related_entities: [服务发现, 微服务架构, Nacos, Eureka, 健康检查, 负载均衡, 容器化]
- bridge_sentence: 服务注册中心存储微服务实例元数据并支持健康检查，是服务发现与负载均衡动态路由的数据源。
- domain: backend

## 镜像仓库
- related_entities: [Docker, Kubernetes, CI/CD, 容器化, Harbor, 版本管理, DevOps]
- bridge_sentence: 镜像仓库存储与分发 Docker 镜像，Harbor 是其企业级方案，是 CI/CD 流水线到 Kubernetes 部署的制品中转站。
- domain: devops

## 版本控制
- related_entities: [Git, CI/CD, GitOps, 分支策略, 代码管理, DevOps, 协作]
- bridge_sentence: 版本控制以 Git 追踪代码变更，分支策略驱动 CI/CD 与 GitOps，是 DevOps 协作与代码管理的基础设施。
- domain: devops

## 声明式配置
- related_entities: [Kubernetes, Terraform, GitOps, Helm, 期望状态, 配置管理, DevOps]
- bridge_sentence: 声明式配置描述期望状态而非操作步骤，Kubernetes 与 Terraform 均基于此，是 GitOps 与 IaC 的共同范式。
- domain: devops