ALTER TABLE "websites" ADD COLUMN "storage_prefix" varchar(160) DEFAULT '' NOT NULL;
ALTER TABLE "websites" ALTER COLUMN "storage_prefix" DROP DEFAULT;
CREATE UNIQUE INDEX "uniq_website_storage_prefix" ON "websites" ("storage_prefix") WHERE NOT ("storage_prefix" = '');
