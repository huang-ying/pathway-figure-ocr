Pathway Figure OCR
===
The goal of this project is to extract identifyable genes, proteins and metabolites from publised pathway figures. In addition to all the code for assembling and running the Pathway Figure OCR pipeline, this repo contains scripts specific to the QC, analysis and figure generation involved in our publications of the work. Here we document a few of the key files and folders relevant to each paper:

* [25 Years of Pathway Figures (BioRxiv 2020)](https://www.biorxiv.org/content/10.1101/2020.05.29.124503v1)
  * Interactive search tool for 65k pathway figures and their gene content: [shiny app](https://gladstone-bioinformatics.shinyapps.io/shiny-25years) and [code](shiny-25years)
  * NIH Figshare of [identified pathway figures](https://doi.org/10.1101/2020.05.29.124503) and [OCR results](https://doi.org/10.1101/2020.05.29.124503) and RDS datasets
  * UpSet plot of top text and figure genes: [script]()
  * Pie chart data for top disease terms for text and figure genes: [script]()
  * Overlap matrix for Hippo Signaling pathway figure genes: [folder]()
  * Machine learning progression plots: [script]()
  * Local database name: `pfocr20200131`
  
* [Identifying Genes in Published Pathway Figure Images (BioRxiv 2018)](https://www.biorxiv.org/content/10.1101/379446v1)
  * Performance assessment figures: [folder](performance)
  * Local database name: `pfocr2018121717`

This work is supported by NIGMS, [R01GM100039](https://app.dimensions.ai/details/grant/grant.2521530)

### Developers
The [codebook](codebook.md) is a good place to start to see how we assemble and run the PFOCR pipeline. Be forewarned, however, this project is still in development and is not ready for production or even dev releases. So, don't expect things to work :)
Contact us via [Issues](issues) if you're interested in contributing to the development. All our code are open source.
