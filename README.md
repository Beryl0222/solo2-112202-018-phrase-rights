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

## 运行资料检查

使用 CPython 3.11.2 和标准库。资料检查仅读取输入。

```sh
python3 pack_check.py
python3 -m unittest -v
```
