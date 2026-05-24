import { Fragment } from "react";
import { Tag, Typography, theme } from "antd";
import { LockOutlined } from "@ant-design/icons";
import { PROPERTY_SOURCE_ORDER, PROPERTY_SOURCE_TAGS } from "../../theme/tagColors";

/**
 * Taxonomy legend for the five property-source categories: swatch (antd Tag) +
 * label + one-line meaning. Sits adjacent to the property/schema table so the
 * source tag in each row is self-explanatory. Colours come from the shared
 * `PROPERTY_SOURCE_TAGS` map ([CLI-45](/CLI/issues/CLI-45) owns the palette) —
 * no local colour map here.
 */
export function PropertyTagLegend() {
  const { token } = theme.useToken();
  return (
    <div
      role="list"
      aria-label="Property source legend"
      style={{
        display: "grid",
        gridTemplateColumns: "max-content 1fr",
        columnGap: token.paddingSM,
        rowGap: token.paddingXXS,
        alignItems: "baseline",
      }}
    >
      {PROPERTY_SOURCE_ORDER.map((source) => {
        const tag = PROPERTY_SOURCE_TAGS[source];
        return (
          <Fragment key={source}>
            <Tag role="listitem" color={tag.color} style={{ marginInlineEnd: 0 }}>
              {tag.locked && <LockOutlined />} {tag.label}
            </Tag>
            <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
              {tag.meaning}
            </Typography.Text>
          </Fragment>
        );
      })}
    </div>
  );
}
