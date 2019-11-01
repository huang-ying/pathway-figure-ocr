# curator - update figure number, title and caption

library(shiny)
library(filesstrings)  
library(magrittr)

## LOCAL INFO PER INSTALLATION
fetch.path <- "/git/wikipathways/pathway-figure-ocr/20191020"
image.path <- paste(fetch.path, "images", "pathway", sep = '/')


## Read in PFOCR fetch results
setwd(fetch.path)
pmc.df.all <- readRDS("pfocr_pathway.rds")
fig.list <- pmc.df.all[,1]
# set headers for output files
headers <- c(names(pmc.df.all), "cur.figtype")
fn <- (paste(image.path,paste0("pfocr_curated.rds"),sep = '/'))
if(!file.exists(fn)){
  df <- data.frame(matrix(ncol=10,nrow=0))
  names(df)<-headers
  saveRDS(df, fn)
}


getFigListTodo <- function(){
  fn <- paste(image.path,x,paste0("pfocr_curated.rds"),sep = '/')
  data <- readRDS(fn)
  fig.list.done <<-data[,1]
  setdiff(fig.list, fig.list.done)
}

saveChoice <- function(df){
  fn <- paste(image.path,x,paste0("pfocr_curated.rds"),sep = '/')
  df.old <- readRDS(fn)
  names(df) <- names(df.old)
  df.new <- rbind(df.old,df)
  saveRDS(df.new, fn)
}

# SHINY UI
ui <- fluidPage(
  titlePanel("PFOCR Curator"),
  
  sidebarLayout(
    sidebarPanel(
      fluidPage(
        # Figure information
        textOutput("fig.count"),
        h5("Current figure"),
        textOutput("fig.name"),
        uiOutput("url"),
        # textOutput("reftext"),
        p(),
        textInput("fig.num", "Figure number","NA"),
        textAreaInput("fig.title", "Figure title", "NA", width = "100%",rows = 3, resize = "vertical" ),
        textAreaInput("fig.caption", "Figure caption", "NA", width = "100%", rows = 6, resize = "vertical" ),
        
        hr(),
        # Buttons
        actionButton("save", label = "Save")
      ),
      width = 7
    ),
    
    mainPanel(
      imageOutput("figure"),
      width = 5
    )
  )
)

# SHINY SERVER
server <- function(input, output, session) {
  
  ## FUNCTION: retrieve next figure
  nextFigure <- function(){
    # Display remaining count and select next figure to process
    fig.list.todo <- getFigListTodo() 
    fig.cnt <- length(fig.list.todo)
    output$fig.count <- renderText({paste(fig.cnt,"figures remaining")})
    if (fig.cnt == 0){
      #TODO: fail gracefully
      # shinyjs::disable("keep") ## not working...
      # shinyjs::disable("trash")
    }
    # Get next fig info
    df <- pmc.df.all %>% 
      filter(pmc.figid==fig.list.todo[1])  %>% 
      droplevels()
    # output$reftext <- renderText({as.character(df$pmc.reftext)})
    figname <- df$pmc.filename
    pmcid <- df$pmc.pmcid
    output$fig.name <- renderText({as.character(df$pmc.filename)})
    ## retrieve image from local
    output$figure <- renderImage({
      list(src = paste(image.path,figname, sep = '/'),
           alt = "No image available",
           width="600px")
    }, deleteFile = FALSE)
    updateTextInput(session, "fig.num", value=df$pmc.number) 
    updateTextInput(session, "fig.title", value=df$pmc.figtitle) 
    updateTextInput(session, "fig.caption", value=df$pmc.caption) 
    pmc.url <- paste0("https://www.ncbi.nlm.nih.gov/pmc/articles/",pmcid)
    display.url <- a(pmcid, href=pmc.url)
    output$url <- renderUI({display.url})
    
    return(df)
  }
  fig <- nextFigure()
  
  ## DEFINE SHARED VARS
  rv <- reactiveValues(fig.df=fig)  

  ## FUNCTION: override rv with input values
  getInputValues <- function(df) {
    df$fig.df$pmc.number <- input$fig.num 
    df$fig.df$pmc.figtitle <- input$fig.title
    df$fig.df$pmc.caption <- input$fig.caption
    return(df)
  }
  
  ## BUTTON FUNCTIONALITY
  observeEvent(input$save, {
    rv <- getInputValues(rv)
    saveChoice(rv$fig.df)
    rv$fig.df <- nextFigure()
  })
  
}

shinyApp(ui = ui, server = server)