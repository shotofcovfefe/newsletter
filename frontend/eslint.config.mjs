import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "@typescript-eslint/no-unused-vars": "warn",       // Downgrade to warning
      "@typescript-eslint/no-explicit-any": "off",       // Allow `any` temporarily
      "react/no-unescaped-entities": "off",               // Allow unescaped ’ and other characters
      "no-unused-expressions": "warn",                    // (optional) don’t block build on this
    },
  },
];

export default eslintConfig;
