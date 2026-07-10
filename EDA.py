import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


DATA_PATH = Path("Data/preprocessed_data.csv")
OUTPUT_DIR = Path("EDA_Outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def load_and_prepare_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    for col in ["price", "area_sqm", "bedrooms", "bathrooms", "area_sqft", "price_per_sqm", "amenities_count", "total_rooms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["price", "area_sqm", "bedrooms", "bathrooms"])
    df["property_type"] = df["property_type"].fillna("Unknown")
    df["furnishing_status"] = df["furnishing_status"].fillna("Unknown")
    df["region"] = df["region"].fillna("Unknown")
    return df


def save_plot(fig, filename: str) -> None:
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=300, bbox_inches="tight")
    plt.close(fig)


def property_characteristics(df: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid")

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("Section 6: Property Characteristics Analysis", fontsize=16, fontweight="bold")

    sns.scatterplot(data=df, x="area_sqm", y="price", hue="property_type", alpha=0.7, ax=axes[0, 0])
    axes[0, 0].set_title("Price vs Area")
    axes[0, 0].set_xlabel("Area (sqm)")
    axes[0, 0].set_ylabel("Price")

    sns.scatterplot(data=df, x="bedrooms", y="price", hue="property_type", alpha=0.7, ax=axes[0, 1])
    axes[0, 1].set_title("Price vs Bedrooms")
    axes[0, 1].set_xlabel("Bedrooms")
    axes[0, 1].set_ylabel("Price")

    sns.scatterplot(data=df, x="bathrooms", y="price", hue="property_type", alpha=0.7, ax=axes[0, 2])
    axes[0, 2].set_title("Price vs Bathrooms")
    axes[0, 2].set_xlabel("Bathrooms")
    axes[0, 2].set_ylabel("Price")

    sns.boxplot(data=df, x="property_type", y="price", ax=axes[1, 0])
    axes[1, 0].set_title("Price Distribution by Property Type")
    axes[1, 0].set_xlabel("Property Type")
    axes[1, 0].set_ylabel("Price")
    axes[1, 0].tick_params(axis="x", rotation=45)

    sns.boxplot(data=df, x="furnishing_status", y="price", ax=axes[1, 1])
    axes[1, 1].set_title("Price Distribution by Furnishing Status")
    axes[1, 1].set_xlabel("Furnishing Status")
    axes[1, 1].set_ylabel("Price")
    axes[1, 1].tick_params(axis="x", rotation=45)

    sns.histplot(df["area_sqm"], bins=30, kde=True, ax=axes[1, 2])
    axes[1, 2].set_title("Area Distribution")
    axes[1, 2].set_xlabel("Area (sqm)")
    axes[1, 2].set_ylabel("Count")

    save_plot(fig, "property_characteristics.png")


def amenities_analysis(df: pd.DataFrame) -> None:
    amenity_cols = [col for col in df.columns if col.startswith("amenity_")]
    amenity_summary = []

    for col in amenity_cols:
        mask = df[col].fillna(0).astype(int).eq(1)
        if mask.sum() == 0:
            continue

        amenity_summary.append(
            {
                "amenity": col.replace("amenity_", "").replace("_", " ").title(),
                "frequency": int(mask.sum()),
                "avg_price_with": df.loc[mask, "price"].mean(),
                "avg_price_without": df.loc[~mask, "price"].mean(),
                "avg_area_with": df.loc[mask, "area_sqm"].mean(),
                "avg_area_without": df.loc[~mask, "area_sqm"].mean(),
                "price_diff": df.loc[mask, "price"].mean() - df.loc[~mask, "price"].mean(),
            }
        )

    amenity_summary_df = pd.DataFrame(amenity_summary).sort_values("frequency", ascending=False)
    amenity_summary_df.to_csv(OUTPUT_DIR / "amenity_summary.csv", index=False)

    fig, axes = plt.subplots(4, 1, figsize=(18, 24))
    fig.suptitle("Section 7: Amenities Analysis", fontsize=16, fontweight="bold")

    sns.barplot(data=amenity_summary_df, x="amenity", y="frequency", ax=axes[0], palette="viridis")
    axes[0].set_title("Amenity Frequency")
    axes[0].set_xlabel("Amenity")
    axes[0].set_ylabel("Properties with Amenity")
    axes[0].tick_params(axis="x", rotation=45)

    sns.barplot(data=amenity_summary_df, x="amenity", y="avg_price_with", ax=axes[1], palette="magma")
    axes[1].set_title("Average Property Price When Amenity Is Present")
    axes[1].set_xlabel("Amenity")
    axes[1].set_ylabel("Average Price")
    axes[1].tick_params(axis="x", rotation=45)

    sns.barplot(data=amenity_summary_df, x="amenity", y="avg_area_with", ax=axes[2], palette="rocket")
    axes[2].set_title("Average Area When Amenity Is Present")
    axes[2].set_xlabel("Amenity")
    axes[2].set_ylabel("Average Area (sqm)")
    axes[2].tick_params(axis="x", rotation=45)

    sns.barplot(data=amenity_summary_df, x="amenity", y="price_diff", ax=axes[3], palette="coolwarm")
    axes[3].set_title("Price Difference (With Amenity - Without Amenity)")
    axes[3].set_xlabel("Amenity")
    axes[3].set_ylabel("Average Price Difference")
    axes[3].tick_params(axis="x", rotation=45)

    save_plot(fig, "amenities_analysis.png")


def relationship_analysis(df: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid")

    numeric_cols = ["price", "area_sqm", "bedrooms", "bathrooms", "amenities_count", "total_rooms", "price_per_sqm"]
    corr_matrix = df[numeric_cols].corr(numeric_only=True)

    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.suptitle("Section 8: Relationship Analysis", fontsize=16, fontweight="bold")

    sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="coolwarm", ax=axes[0, 0])
    axes[0, 0].set_title("Correlation Matrix")

    sns.regplot(data=df, x="area_sqm", y="price", scatter_kws={"alpha": 0.5}, line_kws={"color": "red"}, ax=axes[0, 1])
    axes[0, 1].set_title("Regression: Price vs Area")
    axes[0, 1].set_xlabel("Area (sqm)")
    axes[0, 1].set_ylabel("Price")

    sns.regplot(data=df, x="bedrooms", y="price", scatter_kws={"alpha": 0.5}, line_kws={"color": "red"}, ax=axes[1, 0])
    axes[1, 0].set_title("Regression: Price vs Bedrooms")
    axes[1, 0].set_xlabel("Bedrooms")
    axes[1, 0].set_ylabel("Price")

    sns.regplot(data=df, x="bathrooms", y="price", scatter_kws={"alpha": 0.5}, line_kws={"color": "red"}, ax=axes[1, 1])
    axes[1, 1].set_title("Regression: Price vs Bathrooms")
    axes[1, 1].set_xlabel("Bathrooms")
    axes[1, 1].set_ylabel("Price")

    save_plot(fig, "relationship_analysis.png")

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    sns.boxplot(data=df, x="property_type", y="price", ax=axes[0])
    axes[0].set_title("Price by Property Type")
    axes[0].tick_params(axis="x", rotation=45)

    sns.boxplot(data=df, x="furnishing_status", y="area_sqm", ax=axes[1])
    axes[1].set_title("Area by Furnishing Status")
    axes[1].tick_params(axis="x", rotation=45)
    save_plot(fig, "numerical_vs_categorical.png")

    categorical_counts = pd.crosstab(df["property_type"], df["furnishing_status"])
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    sns.heatmap(categorical_counts, annot=True, fmt="d", cmap="Blues", ax=axes[0])
    axes[0].set_title("Property Type vs Furnishing Status")
    axes[0].set_xlabel("Furnishing Status")
    axes[0].set_ylabel("Property Type")

    categorical_counts_pct = categorical_counts.div(categorical_counts.sum(axis=1), axis=0)
    categorical_counts_pct.plot(kind="bar", stacked=True, ax=axes[1], figsize=(10, 6))
    axes[1].set_title("Stacked Bar: Property Type by Furnishing Status")
    axes[1].set_xlabel("Property Type")
    axes[1].set_ylabel("Share")
    axes[1].legend(title="Furnishing Status", bbox_to_anchor=(1.02, 1), loc="upper left")
    save_plot(fig, "categorical_vs_categorical.png")

    # Print key insights
    corr_summary = corr_matrix["price"].drop("price").sort_values(ascending=False)
    print("Top positive relationships with price:")
    print(corr_summary.head(5).to_string())
    print("\nTop negative relationships with price:")
    print(corr_summary.tail(5).to_string())


def main() -> None:
    df = load_and_prepare_data(DATA_PATH)
    print(f"Loaded dataset with {df.shape[0]} rows and {df.shape[1]} columns.")

    property_characteristics(df)
    amenities_analysis(df)
    relationship_analysis(df)

    print(f"All plots saved in {OUTPUT_DIR.resolve()}.")


if __name__ == "__main__":
    main()
