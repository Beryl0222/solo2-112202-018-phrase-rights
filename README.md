# 代工外观评语的品牌用语发布

业务资料使用虚构编号和合成叙述。文本保持来件拼写和措辞。各表是独立的来源记录。
TSV 文件采用 UTF-8，首行为列名。行首 id 是该表的稳定记录号，空格和标点属于原文，空单元格表示来件未填。
日期时间采用所在地本地时间。资料内注明为编号列表的字段用竖线分隔。

## 资料字段

- `materials/comments.tsv`。layout 由拍摄组记录照片编号及样片位置。reply_to 可指上一次评样 id。
- `materials/glossary.tsv`。photo_right 写明允许文本覆盖位置，market 定义实际销售版，name 是品牌给出的正式叫法。
- `materials/outlets.tsv`。style 为渠道最终实物呈现方式。orders 仅记录实际订单中见到的色名。
- `materials/assets.tsv`。layout 是拍摄图，region 为原片登记的可写范围，retain 记录编辑要求保留的辨样依据。
- `materials/requests.tsv`。order 为已成交记录编号，received 是导购登记时点。body 保留顾客原话。
- `materials/catalog_views.tsv`。导购实际使用的渠道用语及商品样色登记，草稿不对用户开放。
- `materials/order_views.tsv`。订单快照保留结账时顾客的选择和当时渠道稿。

## 运行资料检查

使用 CPython 3.11.2 和标准库。资料检查仅读取输入。

```sh
python3 pack_check.py
python3 -m unittest -v
```

## 工作底稿（colorway）

`colorway` 把资料包整理成三个角色可用的底稿，所有结论都带原始记录号。

```sh
python3 -m colorway.cli                # 渠道、名称、发布、改单总简报
python3 -m colorway.cli --outlet O1    # 只看一个渠道
python3 -m colorway.cli --orders       # 改单处理结果
python3 -m colorway.cli --json out/workspace.json
python3 -m colorway.cli --check        # 有待确认或不可发布项时退出码 1
```

模块分工：

| 模块 | 作用 |
| --- | --- |
| `colorway/comments.py` | 把评语切成实物指代、观看条件、明示采用、推迟和否定片段 |
| `colorway/design.py` | 回复链、采用范围、颜色多义时需设计师确认的叫法 |
| `colorway/names.py` | 色名作用域、同词多样/同样多名、按市场与时点解析候选 |
| `colorway/rights.py` | 解析 `photo_right`：按拍摄版式区分可叠字、可裁、只可整图、不可发布 |
| `colorway/publication.py` | 渠道约束、自足说明、删词时必须保留的辨样依据 |
| `colorway/release.py` | 本地化商品用语、图文关联、多套合规版本、不可发布范围 |
| `colorway/editorial.py` | 已上线图卡与草稿的处置、新词实际可用渠道 |
| `colorway/orders.py` | 旧称改单：位置、时点、实物特征、顾客确认与已承诺颜色 |
| `colorway/compile.py` | 汇总为一份可序列化的工作底稿 |

判读规则：

- 暖光、日光、灯下、“像石蓝”一类只是观看条件；评语和设计师明示采用都不覆盖交付时的官方色名。
- 正式名以品牌词表为准；渠道上线名、旧换季区域名、草稿单独标注，不能跨品牌或跨市场挪用。
- 同一地区的同一个词指到两块样时，先列能分出实物的选项，不由系统替顾客选。
- 只有顾客在来信里确认换成哪块样，才改订单；后续“还是原来的”回到该顾客最近一次确认的快照。
- 渠道会裁图时，单卡必须自带样号、位置和保留的图记；动不得的原片直接列为不可发布。

新增一次评样或新市场只需在 `materials/` 增行；编号关联由 `materials/tables.json` 校验。

